from app.services.github_fetcher import GithubFetcher
from app.services.scorer import Scorer
from app.models import Skill
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import logging
import time
from datetime import datetime, timedelta
from typing import Optional
import threading
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SyncService:
    # 类变量用于跟踪全局同步状态
    _sync_lock = threading.Lock()
    _last_sync_time: Optional[datetime] = None
    _is_syncing = False
    _sync_task: Optional[threading.Thread] = None
    MAX_ITEMS = 4500  # 最大抓取数量
    RATE_LIMIT_SLEEP = 60  # 限流时基础等待时间（秒）

    def __init__(self, db: Session):
        self.db = db
        self.fetcher = GithubFetcher()
        self.processed_repos = set()  # 用于去重

    def sync_with_limit(self, is_auto_sync: bool = False):
        """带数量限制的同步方法
        Args:
            is_auto_sync: 是否是自动同步（自动同步只抓取增量数据）
        """
        try:
            with self.__class__._sync_lock:
                if self.__class__._is_syncing:
                    logger.info("Sync already in progress, skipping...")
                    return {"message": "Sync already in progress", "status": "busy"}
                self.__class__._is_syncing = True
                self.__class__._last_sync_time = datetime.now()

            start_time = time.time()

            # 如果是自动同步，只抓取少量数据
            if is_auto_sync:
                target_items = min(500, self.MAX_ITEMS)  # 自动同步只抓500条
                logger.info(f"Starting AUTO sync with limit {target_items} items...")
            else:
                target_items = self.MAX_ITEMS
                logger.info(f"Starting MANUAL sync with limit {target_items} items...")

            all_data = []
            page = 1
            max_pages = 3 if is_auto_sync else 10  # 自动同步只抓3页
            consecutive_empty = 0
            max_consecutive_empty = 2

            # 获取已存在的仓库名（用于增量同步）
            existing_repos = set()
            if is_auto_sync:
                existing = self.db.query(Skill.name).all()
                existing_repos = {r[0] for r in existing}
                logger.info(f"Found {len(existing_repos)} existing repos in database")

            # 使用 fetcher 中的关键词列表
            keywords = self.fetcher.keywords
            logger.info(f"Using keywords: {keywords}")

            # 1. 从 GitHub 抓取数据
            while len(all_data) < target_items and page <= max_pages:
                page_has_data = False

                # 随机打乱关键词顺序，避免总是相同顺序
                random.shuffle(keywords)

                for keyword in keywords:
                    if len(all_data) >= target_items:
                        break

                    try:
                        # 检查是否接近超时
                        elapsed = time.time() - start_time
                        if elapsed > 250:  # 预留50秒处理时间
                            logger.warning(f"Approaching timeout ({elapsed:.0f}s), stopping fetch")
                            break

                        logger.info(f"Searching keyword '{keyword}' page {page}")
                        repos = self.fetcher.search(keyword, page=page)

                        if repos:
                            page_has_data = True
                            logger.info(f"Found {len(repos)} repos for '{keyword}' page {page}")

                        for repo in repos:
                            if len(all_data) >= target_items:
                                break

                            try:
                                repo_name = repo['name']
                                repo_full_name = f"{repo['owner']['login']}/{repo_name}"

                                # 检查是否已存在
                                if repo_full_name in self.processed_repos:
                                    continue

                                # 自动同步时，跳过已存在的仓库
                                if is_auto_sync and repo_name in existing_repos:
                                    logger.debug(f"Skipping existing repo: {repo_name}")
                                    continue

                                # 随机延迟避免限流
                                time.sleep(random.uniform(0.1, 0.3))

                                details = self.fetcher.fetch_repo_details(repo)
                                if details:
                                    details["full_name"] = repo_full_name
                                    all_data.append(details)
                                    self.processed_repos.add(repo_full_name)
                                    logger.info(f"Added: {repo_full_name} (Total: {len(all_data)})")

                            except Exception as e:
                                logger.error(f"Error processing {repo.get('name')}: {e}")
                                continue

                    except Exception as e:
                        logger.error(f"Error with keyword {keyword}: {e}")

                        # 如果是限流错误，等待后继续
                        if "rate limit" in str(e).lower() or "403" in str(e):
                            logger.warning("Rate limit detected, sleeping for 60 seconds...")
                            time.sleep(60)

                        continue

                page += 1

                # 检查是否连续无数据
                if not page_has_data:
                    consecutive_empty += 1
                    logger.info(f"Page {page-1} had no data, consecutive empty: {consecutive_empty}")
                else:
                    consecutive_empty = 0

                if consecutive_empty >= max_consecutive_empty:
                    logger.info(f"No more data after {consecutive_empty} consecutive empty pages")
                    break

            logger.info(f"Total fetched unique items: {len(all_data)}")

            if not all_data:
                logger.warning("No new data fetched")
                return {
                    "inserted": 0,
                    "updated": 0,
                    "skipped": 0,
                    "total": 0,
                    "message": "No new data fetched",
                    "elapsed_seconds": round(time.time() - start_time, 2)
                }

            # 2. 计算评分和保存数据
            result = self._process_and_save_data(all_data)

            elapsed_time = time.time() - start_time
            result["elapsed_seconds"] = round(elapsed_time, 2)
            result["is_auto_sync"] = is_auto_sync

            logger.info(f"✅ Sync completed in {elapsed_time:.2f}s: "
                       f"{result.get('inserted', 0)} inserted, {result.get('updated', 0)} updated")

            return result

        except Exception as e:
            logger.error(f"Error in sync_with_limit: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.db.rollback()
            return {"error": str(e), "message": "Sync failed"}
        finally:
            with self.__class__._sync_lock:
                self.__class__._is_syncing = False
            self.processed_repos.clear()  # 清理内存

    def _process_and_save_data(self, all_data):
        """处理和保存数据"""
        # 计算评分
        logger.info(f"Calculating scores for {len(all_data)} items...")
        scored_data = Scorer(all_data).calculate()

        allowed_fields = Skill.__table__.columns.keys()

        updated_count = 0
        inserted_count = 0
        skipped_count = 0
        error_count = 0

        # 批量处理数据（更小的批次）
        batch_size = 20
        total_batches = (len(scored_data) + batch_size - 1) // batch_size

        for batch_num, i in enumerate(range(0, len(scored_data), batch_size), 1):
            batch = scored_data[i:i + batch_size]
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} items)")

            for item in batch:
                try:
                    # 过滤字段
                    clean_item = {}
                    for k, v in item.items():
                        if k in allowed_fields and k not in ['full_name']:
                            if k == 'last_commit' and isinstance(v, str):
                                try:
                                    from datetime import datetime
                                    v = datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ")
                                except:
                                    v = datetime.utcnow()
                            clean_item[k] = v

                    if 'name' not in clean_item:
                        skipped_count += 1
                        continue

                    # 查询是否存在
                    existing_skill = self.db.query(Skill).filter(
                        Skill.name == clean_item["name"]
                    ).first()

                    if existing_skill:
                        # 更新现有记录
                        for key, value in clean_item.items():
                            setattr(existing_skill, key, value)
                        updated_count += 1
                        logger.debug(f"Updated: {clean_item['name']}")
                    else:
                        # 创建新记录
                        try:
                            new_skill = Skill(**clean_item)
                            self.db.add(new_skill)
                            inserted_count += 1
                            logger.debug(f"Inserted: {clean_item['name']}")
                        except Exception as e:
                            logger.error(f"Error creating skill {clean_item.get('name')}: {e}")
                            error_count += 1
                            continue

                except Exception as e:
                    logger.error(f"Error processing item: {e}")
                    error_count += 1
                    continue

            # 每批提交
            try:
                self.db.commit()
                logger.info(f"Batch {batch_num} committed: "
                          f"Inserted: {inserted_count}, Updated: {updated_count}, "
                          f"Skipped: {skipped_count}, Errors: {error_count}")
            except Exception as e:
                self.db.rollback()
                logger.error(f"Error in batch commit: {e}")

                # 尝试逐条提交
                logger.info("Retrying with individual commits...")
                for item in batch:
                    try:
                        self.db.commit()
                    except:
                        self.db.rollback()

        return {
            "inserted": inserted_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "errors": error_count,
            "total_fetched": len(all_data)
        }

    @classmethod
    def start_auto_sync(cls, db_factory):
        """启动自动同步任务（改进版）"""
        if cls._sync_task and cls._sync_task.is_alive():
            logger.info("Auto sync task already running")
            return

        def sync_worker():
            """工作线程函数"""
            consecutive_failures = 0
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
                            # 自动同步模式：只抓增量数据
                            result = service.sync_with_limit(is_auto_sync=True)
                            logger.info(f"Auto sync result: {result}")
                            consecutive_failures = 0
                        except Exception as e:
                            logger.error(f"Auto sync failed: {e}")
                            consecutive_failures += 1
                        finally:
                            db.close()
                    else:
                        logger.debug(f"Auto sync check: should_sync={should_sync}, is_syncing={cls._is_syncing}")

                    # 动态调整检查间隔
                    if consecutive_failures > 3:
                        sleep_time = 300  # 失败多次后，5分钟检查一次
                    else:
                        sleep_time = 60  # 正常情况1分钟检查一次

                    time.sleep(sleep_time)

                except Exception as e:
                    logger.error(f"Error in auto sync worker: {e}")
                    time.sleep(300)  # 出错后等待5分钟

        cls._sync_task = threading.Thread(target=sync_worker, daemon=True)
        cls._sync_task.start()
        logger.info("Auto sync task started")