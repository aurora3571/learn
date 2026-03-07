from app.services.github_fetcher import GithubFetcher
from app.services.scorer import Scorer
from app.models import Skill
from sqlalchemy.orm import Session
import logging
import time
from datetime import datetime, timedelta
from typing import Optional
import threading
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SyncService:
    _sync_lock = threading.RLock()
    _last_sync_time: Optional[datetime] = None
    _is_syncing = False
    _sync_task: Optional[threading.Thread] = None
    MAX_ITEMS = 5000
    BATCH_SIZE = 100

    def __init__(self, db: Session):
        self.db = db
        self.fetcher = GithubFetcher()
        self.processed_repos = set()

    def sync_with_limit(self, is_auto_sync: bool = False):
        """超快速同步方法"""
        try:
            with self.__class__._sync_lock:
                if self.__class__._is_syncing:
                    return {"message": "Sync already in progress", "status": "busy"}
                self.__class__._is_syncing = True
                self.__class__._last_sync_time = datetime.now()

            start_time = time.time()
            sync_type = "AUTO" if is_auto_sync else "MANUAL"
            
            # 动态调整目标数量
            target_items = min(1500 if is_auto_sync else self.MAX_ITEMS, self.MAX_ITEMS)
            
            logger.info(f"🚀 Starting {sync_type} sync (目标: {target_items} 条)")

            # 重置请求计数
            GithubFetcher.reset_request_count()
            
            all_data = []
            page = 1
            max_pages = 4 if is_auto_sync else 12
            consecutive_empty = 0

            # 使用所有关键词，分批处理
            keywords = self.fetcher.keywords
            keyword_batches = [keywords[i:i+5] for i in range(0, len(keywords), 5)]

            # 快速抓取模式
            while len(all_data) < target_items and page <= max_pages:
                if GithubFetcher.should_stop():
                    logger.info(f"⛔ 达到请求上限，停止于 {len(all_data)} 条")
                    break

                batch_repos = []
                
                # 并行搜索多个关键词批次
                with ThreadPoolExecutor(max_workers=3) as executor:
                    future_to_batch = {
                        executor.submit(self.fetcher.search_batch, batch, page): batch
                        for batch in keyword_batches[:3]  # 同时处理3个批次
                    }
                    
                    for future in as_completed(future_to_batch):
                        if GithubFetcher.should_stop():
                            break
                        try:
                            repos = future.result(timeout=15)
                            if repos:
                                batch_repos.extend(repos)
                        except Exception as e:
                            logger.error(f"Batch search error: {e}")

                if batch_repos:
                    # 快速去重
                    unique_repos = {}
                    for repo in batch_repos:
                        repo_id = repo['id']
                        if repo_id not in unique_repos:
                            unique_repos[repo_id] = repo
                    
                    repos_to_fetch = list(unique_repos.values())[:60]  # 最多取60条
                    
                    logger.info(f"📦 批量获取 {len(repos_to_fetch)} 个仓库详情")
                    
                    # 分批次获取详情
                    details = self.fetcher.fetch_repo_details_batch(repos_to_fetch)
                    
                    # 快速去重
                    for detail in details:
                        if detail and detail['name'] not in self.processed_repos:
                            all_data.append(detail)
                            self.processed_repos.add(detail['name'])
                    
                    consecutive_empty = 0
                    
                    # 计算速度
                    elapsed = time.time() - start_time
                    speed = len(all_data) / elapsed if elapsed > 0 else 0
                    logger.info(f"📊 进度: {len(all_data)}/{target_items} 条 | 速度: {speed:.1f} 条/秒")
                else:
                    consecutive_empty += 1
                    logger.info(f"⚠️ 第 {page} 页无数据")

                page += 1
                
                if consecutive_empty >= 2:
                    logger.info("✅ 无更多数据可用")
                    break

            logger.info(f"✅ 共获取 {len(all_data)} 条唯一数据")

            if not all_data:
                return {
                    "inserted": 0,
                    "updated": 0,
                    "total": 0,
                    "message": "未获取到数据",
                    "elapsed_seconds": round(time.time() - start_time, 2)
                }

            # 快速处理数据
            result = self._fast_process_data(all_data)
            
            stats = self.fetcher.get_request_stats()
            result["api_stats"] = stats

            elapsed_time = time.time() - start_time
            result["elapsed_seconds"] = round(elapsed_time, 2)
            result["sync_type"] = sync_type

            # 计算最终速度
            avg_speed = len(all_data) / elapsed_time
            logger.info(f"⚡ 平均速度: {avg_speed:.1f} 条/秒")
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

    def _fast_process_data(self, all_data):
        """超快速处理数据"""
        try:
            logger.info(f"处理 {len(all_data)} 条数据...")
            
            # 批量计算评分
            scored_data = Scorer(all_data).calculate()
            
            allowed_fields = Skill.__table__.columns.keys()

            updated_count = 0
            inserted_count = 0
            batch_count = 0

            # 超大批次处理
            batch_size = self.BATCH_SIZE
            for i in range(0, len(scored_data), batch_size):
                batch = scored_data[i:i + batch_size]
                batch_count += 1
                
                # 批量处理
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
                            updated_count += 1
                        else:
                            self.db.add(Skill(**clean_item))
                            inserted_count += 1

                    except Exception as e:
                        logger.error(f"处理错误: {e}")

                # 批量提交
                try:
                    self.db.commit()
                    if batch_count % 2 == 0:
                        logger.info(f"批次 {batch_count} 提交: +{inserted_count} 新, {updated_count} 更新")
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