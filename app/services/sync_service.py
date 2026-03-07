from app.services.github_fetcher import GithubFetcher
from app.services.scorer import Scorer
from app.models import Skill
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SyncService:
    # 类变量用于跟踪全局同步状态
    _sync_lock = threading.Lock()
    _last_sync_time: Optional[datetime] = None
    _is_syncing = False
    _sync_task: Optional[threading.Thread] = None
    MAX_ITEMS = 4500  # 最大抓取数量

    def __init__(self, db: Session):
        self.db = db
        self.fetcher = GithubFetcher()

    @classmethod
    def start_auto_sync(cls, db_factory):
        """启动自动同步任务"""
        if cls._sync_task and cls._sync_task.is_alive():
            logger.info("Auto sync task already running")
            return

        def sync_worker():
            """工作线程函数"""
            while True:
                try:
                    # 检查是否需要同步
                    now = datetime.now()
                    should_sync = False

                    with cls._sync_lock:
                        if cls._last_sync_time is None:
                            should_sync = True
                        else:
                            time_diff = now - cls._last_sync_time
                            if time_diff >= timedelta(hours=1):
                                should_sync = True

                    if should_sync and not cls._is_syncing:
                        logger.info("Starting auto sync...")
                        # 创建新的数据库会话
                        db = db_factory()
                        try:
                            service = cls(db)
                            service.sync_with_limit()
                        finally:
                            db.close()

                    # 每分钟检查一次
                    time.sleep(60)

                except Exception as e:
                    logger.error(f"Error in auto sync worker: {e}")
                    time.sleep(60)

        cls._sync_task = threading.Thread(target=sync_worker, daemon=True)
        cls._sync_task.start()
        logger.info("Auto sync task started")

    def sync_with_limit(self):
        """带数量限制的同步方法"""
        try:
            with self.__class__._sync_lock:
                if self.__class__._is_syncing:
                    logger.info("Sync already in progress, skipping...")
                    return {"message": "Sync already in progress"}
                self.__class__._is_syncing = True
                self.__class__._last_sync_time = datetime.now()

            logger.info("Starting sync with limit (max 4500 items)...")
            start_time = time.time()

            keywords = [
                "claude-mcp",
                "agent-tools",
                "codex-skills",
                "ai-agent",
                "llm-agent",
                "langchain",
                "autogpt",
                "babyagi",
                "agent-framework",
                "llm-tool"
            ]

            all_data = []
            page = 1
            consecutive_empty = 0
            max_consecutive_empty = 3  # 连续空结果的最大次数

            # 1. 从 GitHub 抓取数据，直到达到限制或没有更多数据
            while len(all_data) < self.MAX_ITEMS:
                page_empty_count = 0

                for keyword in keywords:
                    if len(all_data) >= self.MAX_ITEMS:
                        break

                    try:
                        # 使用分页获取更多数据
                        repos = self.fetcher.search(keyword, page=page)
                        logger.info(f"Found {len(repos)} repos for keyword: {keyword} (page {page})")

                        if not repos:
                            page_empty_count += 1
                            continue

                        for repo in repos:
                            if len(all_data) >= self.MAX_ITEMS:
                                break

                            try:
                                # 检查是否已存在（避免重复）
                                repo_full_name = f"{repo['owner']['login']}/{repo['name']}"
                                if any(d.get('full_name') == repo_full_name for d in all_data):
                                    continue

                                details = self.fetcher.fetch_repo_details(repo)
                                details["stars"] = repo.get("stargazers_count", 0)
                                details["forks"] = repo.get("forks_count", 0)
                                details["full_name"] = repo_full_name  # 添加全名用于去重
                                all_data.append(details)

                                # 每获取100条数据记录一次进度
                                if len(all_data) % 100 == 0:
                                    logger.info(f"Progress: {len(all_data)}/{self.MAX_ITEMS} items fetched")

                            except Exception as e:
                                logger.error(f"Error fetching details for {repo.get('name')}: {e}")
                                continue

                    except Exception as e:
                        logger.error(f"Error searching keyword {keyword}: {e}")
                        continue

                page += 1

                # 如果连续多次没有新数据，则停止
                if page_empty_count >= len(keywords) * 0.8:  # 80%的关键词没有返回数据
                    consecutive_empty += 1
                else:
                    consecutive_empty = 0

                if consecutive_empty >= max_consecutive_empty:
                    logger.info(f"No more data after {consecutive_empty} consecutive empty pages")
                    break

                # 添加小延迟避免触发限流
                time.sleep(0.5)

            logger.info(f"Total fetched items: {len(all_data)} (limit: {self.MAX_ITEMS})")

            if not all_data:
                logger.warning("No data fetched")
                return {"inserted": 0, "updated": 0, "skipped": 0, "total": 0}

            # 2. 计算评分
            scored_data = Scorer(all_data).calculate()
            allowed_fields = Skill.__table__.columns.keys()

            updated_count = 0
            inserted_count = 0
            skipped_count = 0

            # 3. 批量处理数据（每100条一批）
            batch_size = 100
            for i in range(0, len(scored_data), batch_size):
                batch = scored_data[i:i + batch_size]

                for item in batch:
                    try:
                        # 过滤字段
                        clean_item = {k: v for k, v in item.items() if k in allowed_fields and k != 'full_name'}

                        if 'name' not in clean_item:
                            logger.warning(f"Item missing name field, skipping")
                            skipped_count += 1
                            continue

                        # 先查询是否存在
                        existing_skill = self.db.query(Skill).filter(
                            Skill.name == clean_item["name"]
                        ).first()

                        if existing_skill:
                            # 如果存在，更新所有字段
                            for key, value in clean_item.items():
                                setattr(existing_skill, key, value)
                            updated_count += 1
                        else:
                            # 如果不存在，创建新记录
                            new_skill = Skill(**clean_item)
                            self.db.add(new_skill)
                            inserted_count += 1

                    except Exception as e:
                        logger.error(f"Error processing item {item.get('name', 'unknown')}: {e}")
                        continue

                # 每批提交一次
                try:
                    self.db.commit()
                    logger.info(f"Batch {i//batch_size + 1} committed: {inserted_count} inserted, {updated_count} updated so far")
                except IntegrityError as e:
                    self.db.rollback()
                    logger.error(f"IntegrityError in batch: {e}")
                except Exception as e:
                    self.db.rollback()
                    logger.error(f"Error in batch commit: {e}")

            elapsed_time = time.time() - start_time
            logger.info(f"✅ Sync completed in {elapsed_time:.2f}s: {inserted_count} inserted, {updated_count} updated, {skipped_count} skipped")

            return {
                "inserted": inserted_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "total": inserted_count + updated_count,
                "elapsed_seconds": round(elapsed_time, 2)
            }

        except Exception as e:
            logger.error(f"Error in sync_with_limit: {e}")
            self.db.rollback()
            raise
        finally:
            with self.__class__._sync_lock:
                self.__class__._is_syncing = False

    def sync(self):
        """保持原有的同步方法，但调用新的带限制的方法"""
        return self.sync_with_limit()