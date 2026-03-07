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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SyncService:
    # 类变量用于跟踪全局同步状态
    _sync_lock = threading.RLock()
    _last_sync_time: Optional[datetime] = None
    _is_syncing = False
    _sync_task: Optional[threading.Thread] = None
    MAX_ITEMS = 5000  # 从4500修改为5000
    RATE_LIMIT_SLEEP = 30  # 减少限流等待时间

    def __init__(self, db: Session):
        self.db = db
        self.fetcher = GithubFetcher()
        self.processed_repos = set()

    def sync_with_limit(self, is_auto_sync: bool = False):
        """带数量限制的同步方法"""
        try:
            with self.__class__._sync_lock:
                if self.__class__._is_syncing:
                    return {"message": "Sync already in progress", "status": "busy"}
                self.__class__._is_syncing = True
                self.__class__._last_sync_time = datetime.now()

            start_time = time.time()
            sync_type = "AUTO" if is_auto_sync else "MANUAL"
            target_items = min(1000 if is_auto_sync else self.MAX_ITEMS, self.MAX_ITEMS)
            
            logger.info(f"🚀 Starting {sync_type} sync (max: {target_items} items)")

            # 重置请求计数
            GithubFetcher.reset_request_count()
            
            all_data = []
            page = 1
            max_pages = 5 if is_auto_sync else 20
            consecutive_empty = 0

            keywords = self.fetcher.keywords
            random.shuffle(keywords)

            # 快速抓取模式
            while len(all_data) < target_items and page <= max_pages:
                if GithubFetcher.should_stop():
                    logger.info(f"⛔ Stop signal received at {len(all_data)} items")
                    break

                batch_repos = []
                
                # 批量获取搜索结果
                for keyword in keywords[:10]:  # 限制关键词数量
                    if len(all_data) >= target_items or GithubFetcher.should_stop():
                        break
                    
                    repos = self.fetcher.search(keyword, page=page, per_page=50)  # 减少每页数量
                    if repos:
                        batch_repos.extend(repos[:20])  # 每个关键词最多取20个

                if batch_repos:
                    # 批量获取详情
                    logger.info(f"📦 Fetching details for {len(batch_repos)} repos (batch)")
                    details = self.fetcher.fetch_repo_details_batch(batch_repos)
                    
                    for detail in details:
                        if detail and detail['name'] not in self.processed_repos:
                            all_data.append(detail)
                            self.processed_repos.add(detail['name'])
                            
                            if len(all_data) % 50 == 0:
                                progress = (len(all_data) / target_items) * 100
                                logger.info(f"📊 Progress: {len(all_data)}/{target_items} ({progress:.1f}%)")
                    
                    consecutive_empty = 0
                else:
                    consecutive_empty += 1

                page += 1
                
                if consecutive_empty >= 2:
                    logger.info("No more data available")
                    break

            logger.info(f"✅ Fetched {len(all_data)} unique items")

            if not all_data:
                return {
                    "inserted": 0,
                    "updated": 0,
                    "total": 0,
                    "message": "No data fetched",
                    "elapsed_seconds": round(time.time() - start_time, 2)
                }

            # 计算评分并保存
            result = self._process_and_save_data(all_data)
            
            # 获取请求统计
            stats = self.fetcher.get_request_stats()
            result["api_stats"] = stats

            elapsed_time = time.time() - start_time
            result["elapsed_seconds"] = round(elapsed_time, 2)
            result["sync_type"] = sync_type

            logger.info(f"✅ Sync completed: +{result.get('inserted', 0)} new, "
                       f"{result.get('updated', 0)} updated in {elapsed_time:.1f}s")

            return result

        except Exception as e:
            logger.error(f"Error in sync: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"error": str(e)}
        finally:
            with self.__class__._sync_lock:
                self.__class__._is_syncing = False
            self.processed_repos.clear()

    def _process_and_save_data(self, all_data):
        """快速处理和保存数据"""
        try:
            logger.info(f"Processing {len(all_data)} items...")
            
            # 批量计算评分
            scored_data = Scorer(all_data).calculate()
            
            allowed_fields = Skill.__table__.columns.keys()

            updated_count = 0
            inserted_count = 0

            # 更大的批次处理
            batch_size = 100
            for i in range(0, len(scored_data), batch_size):
                batch = scored_data[i:i + batch_size]
                
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
                        logger.error(f"Error processing item: {e}")
                        continue

                # 每批提交
                try:
                    self.db.commit()
                    logger.info(f"Batch {i//batch_size + 1} committed: +{inserted_count}/{updated_count}")
                except Exception as e:
                    self.db.rollback()
                    logger.error(f"Batch commit failed: {e}")

            return {
                "inserted": inserted_count,
                "updated": updated_count,
                "total_fetched": len(all_data)
            }

        except Exception as e:
            logger.error(f"Error in processing: {e}")
            return {"inserted": 0, "updated": 0, "total_fetched": len(all_data)}

    @classmethod
    def start_auto_sync(cls, db_factory):
        """启动自动同步"""
        if cls._sync_task and cls._sync_task.is_alive():
            return

        def sync_worker():
            while True:
                try:
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
                        db = db_factory()
                        try:
                            service = cls(db)
                            service.sync_with_limit(is_auto_sync=True)
                        finally:
                            db.close()

                    time.sleep(60)

                except Exception as e:
                    logger.error(f"Auto sync error: {e}")
                    time.sleep(300)

        cls._sync_task = threading.Thread(target=sync_worker, daemon=True)
        cls._sync_task.start()
        logger.info("Auto sync started")