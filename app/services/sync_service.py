from app.services.github_fetcher import GithubFetcher
from app.services.scorer import Scorer
from app.models import Skill
from app.config import settings
from sqlalchemy.orm import Session
import logging
import time
from datetime import datetime, timedelta
from typing import Optional
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SyncService:
    _sync_lock = threading.RLock()
    _last_sync_time: Optional[datetime] = None
    _is_syncing = False
    _sync_task: Optional[threading.Thread] = None
    MAX_ITEMS = 5000
    BATCH_SIZE = 100  # 增大批量大小

    def __init__(self, db: Session):
        self.db = db
        self.fetcher = GithubFetcher()
        self.processed_repos = set()

    def sync_with_limit(self, is_auto_sync: bool = False):
        """同步方法 - 优化版"""
        try:
            with self.__class__._sync_lock:
                if self.__class__._is_syncing:
                    return {"message": "Sync already in progress", "status": "busy"}
                self.__class__._is_syncing = True
                self.__class__._last_sync_time = datetime.now()

            start_time = time.time()
            sync_type = "AUTO" if is_auto_sync else "MANUAL"
            
            # 动态调整目标数量
            target_items = min(1000 if is_auto_sync else self.MAX_ITEMS, self.MAX_ITEMS)
            
            logger.info(f"🚀 开始 {sync_type} 同步 (目标: {target_items} 条)")

            # 检查 GitHub Token
            logger.info(f"🔑 GitHub Token 是否存在: {bool(settings.github_token)}")
            
            # 重置请求计数
            GithubFetcher.start_session()
            
            all_data = []
            page = 1
            max_pages = 5 if is_auto_sync else 10  # 增加页数
            consecutive_empty = 0

            keywords = self.fetcher.keywords

            # 第一阶段：快速收集所有仓库
            logger.info("📚 第一阶段：收集仓库列表...")
            all_repos = []
            
            while len(all_repos) < target_items * 3 and page <= max_pages:  # 收集3倍的数据以备去重
                if GithubFetcher.should_stop():
                    logger.info(f"⛔ 达到请求上限，停止于 {len(all_repos)} 条")
                    break

                logger.info(f"📄 处理第 {page} 页...")
                
                page_repos = []
                for keyword in keywords:
                    if GithubFetcher.should_stop():
                        break
                    repos = self.fetcher.search(keyword, page, per_page=30)
                    if repos:
                        page_repos.extend(repos[:15])  # 每个关键词取15条

                if page_repos:
                    all_repos.extend(page_repos)
                    consecutive_empty = 0
                    
                    # 显示进度
                    stats = GithubFetcher.get_request_stats()
                    logger.info(f"📊 收集进度: {len(all_repos)} 个仓库 | 请求: {stats['total_requests']}/5000")
                else:
                    consecutive_empty += 1
                    logger.info(f"⚠️ 第 {page} 页无数据")

                page += 1
                
                if consecutive_empty >= 2:
                    logger.info("✅ 无更多数据")
                    break

            logger.info(f"✅ 第一阶段完成，共收集 {len(all_repos)} 个仓库")

            if not all_repos:
                return {
                    "inserted": 0,
                    "updated": 0,
                    "total": 0,
                    "message": "未获取到数据",
                    "elapsed_seconds": round(time.time() - start_time, 2)
                }

            # 第二阶段：去重并获取详情
            logger.info("📦 第二阶段：获取仓库详情...")
            
            # 去重
            unique_repos = {}
            for repo in all_repos:
                repo_id = repo['id']
                if repo_id not in unique_repos:
                    unique_repos[repo_id] = repo
            
            repos_to_fetch = list(unique_repos.values())[:target_items * 2]  # 取目标数量的2倍
            logger.info(f"📊 去重后剩余 {len(repos_to_fetch)} 个唯一仓库")

            # 批量获取详情
            details = self.fetcher.fetch_repo_details_batch(repos_to_fetch)
            
            # 去重
            for detail in details:
                if detail and detail['name'] not in self.processed_repos:
                    all_data.append(detail)
                    self.processed_repos.add(detail['name'])
                    
                    # 达到目标数量就停止
                    if len(all_data) >= target_items:
                        logger.info(f"✅ 达到目标数量 {target_items} 条")
                        break

            logger.info(f"✅ 第二阶段完成，共获取 {len(all_data)} 条唯一数据")

            if not all_data:
                return {
                    "inserted": 0,
                    "updated": 0,
                    "total": 0,
                    "message": "未获取到数据",
                    "elapsed_seconds": round(time.time() - start_time, 2)
                }

            # 处理数据并保存
            result = self._process_and_save_data(all_data)
            
            stats = GithubFetcher.get_request_stats()
            result["api_stats"] = stats

            elapsed_time = time.time() - start_time
            result["elapsed_seconds"] = round(elapsed_time, 2)
            result["sync_type"] = sync_type

            logger.info(f"✅ 同步完成: +{result.get('inserted', 0)} 新, "
                       f"{result.get('updated', 0)} 更新, 耗时 {elapsed_time:.1f}秒")

            return result

        except Exception as e:
            logger.error(f"同步错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"error": str(e), "message": "同步失败"}
        finally:
            with self.__class__._sync_lock:
                self.__class__._is_syncing = False
            self.processed_repos.clear()

    def _process_and_save_data(self, all_data):
        """处理和保存数据 - 优化批量提交"""
        try:
            logger.info(f"处理 {len(all_data)} 条数据...")
            
            # 计算评分
            scored_data = Scorer(all_data).calculate()
            allowed_fields = Skill.__table__.columns.keys()

            updated_count = 0
            inserted_count = 0

            # 分批处理 - 使用更大的批次
            batch_size = self.BATCH_SIZE
            for i in range(0, len(scored_data), batch_size):
                batch_start = time.time()
                batch = scored_data[i:i + batch_size]
                
                batch_updated = 0
                batch_inserted = 0
                
                for item in batch:
                    try:
                        clean_item = {}
                        for k, v in item.items():
                            if k in allowed_fields and k not in ['full_name']:
                                if k == 'last_commit' and isinstance(v, str):
                                    try:
                                        v = datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ")
                                    except:
                                        v = datetime.utcnow()
                                clean_item[k] = v

                        if 'name' not in clean_item:
                            continue

                        existing = self.db.query(Skill).filter(
                            Skill.name == clean_item["name"]
                        ).first()

                        if existing:
                            for key, value in clean_item.items():
                                setattr(existing, key, value)
                            batch_updated += 1
                        else:
                            self.db.add(Skill(**clean_item))
                            batch_inserted += 1

                    except Exception as e:
                        logger.error(f"处理错误: {e}")

                # 提交批次
                try:
                    self.db.commit()
                    batch_time = time.time() - batch_start
                    updated_count += batch_updated
                    inserted_count += batch_inserted
                    logger.info(f"批次提交: +{batch_inserted} 新, {batch_updated} 更新, 耗时 {batch_time:.2f}秒")
                except Exception as e:
                    self.db.rollback()
                    logger.error(f"提交失败: {e}")

            return {
                "inserted": inserted_count,
                "updated": updated_count,
                "total_fetched": len(all_data)
            }

        except Exception as e:
            logger.error(f"处理错误: {e}")
            return {"inserted": 0, "updated": 0, "total_fetched": len(all_data)}

    @classmethod
    def start_auto_sync(cls, db_factory):
        """启动自动同步"""
        if cls._sync_task and cls._sync_task.is_alive():
            return

        def sync_worker():
            consecutive_failures = 0
            while True:
                try:
                    now = datetime.now()
                    should_sync = False

                    with cls._sync_lock:
                        if cls._last_sync_time is None:
                            should_sync = True
                        else:
                            time_diff = now - cls._last_sync_time
                            if time_diff >= timedelta(hours=2):
                                should_sync = True

                    if should_sync and not cls._is_syncing:
                        logger.info("Starting auto sync...")
                        db = db_factory()
                        try:
                            service = cls(db)
                            result = service.sync_with_limit(is_auto_sync=True)
                            if result.get('inserted', 0) > 0:
                                consecutive_failures = 0
                            else:
                                consecutive_failures += 1
                        except Exception as e:
                            logger.error(f"Auto sync failed: {e}")
                            consecutive_failures += 1
                        finally:
                            db.close()

                    sleep_time = 300 if consecutive_failures > 3 else 120
                    time.sleep(sleep_time)

                except Exception as e:
                    logger.error(f"Auto sync error: {e}")
                    time.sleep(300)

        cls._sync_task = threading.Thread(target=sync_worker, daemon=True)
        cls._sync_task.start()
        logger.info("Auto sync started")