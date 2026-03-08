from app.services.github_fetcher import GithubFetcher
from app.services.scorer import Scorer
from app.models import Skill
from app.config import settings
from sqlalchemy.orm import Session
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import threading
import uuid
from queue import Queue
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    QUEUED = "queued"
    WAITING = "waiting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SyncTask:
    def __init__(self, task_id: str, is_auto_sync: bool = False):
        self.task_id = task_id
        self.is_auto_sync = is_auto_sync
        self.status = TaskStatus.QUEUED
        self.progress = 0
        self.message = "等待开始..."
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None
        self.result = None
        self.error = None
        self.queue_position = 0


class SyncService:
    _sync_lock = threading.RLock()
    _last_sync_time: Optional[datetime] = None
    _is_syncing = False
    
    # 任务队列管理
    _tasks: Dict[str, SyncTask] = {}
    _task_lock = threading.RLock()
    _task_queue = Queue()
    _current_task_id: Optional[str] = None
    
    MAX_ITEMS = 5000
    BATCH_SIZE = 100
    
    # 启动队列处理器
    _queue_processor_started = False
    _queue_processor_thread = None

    def __init__(self, db: Session):
        self.db = db
        self.fetcher = GithubFetcher()
        self.processed_repos = set()

    @classmethod
    def _ensure_queue_processor(cls, db_factory):
        """确保队列处理器在运行"""
        if not cls._queue_processor_started or not cls._queue_processor_thread or not cls._queue_processor_thread.is_alive():
            cls._start_queue_processor(db_factory)

    @classmethod
    def _start_queue_processor(cls, db_factory):
        """启动队列处理器"""
        def process_queue():
            logger.info("🚀 启动任务队列处理器")
            while True:
                try:
                    # 从队列获取任务
                    task_id = cls._task_queue.get()
                    
                    with cls._task_lock:
                        if task_id not in cls._tasks:
                            continue
                        task = cls._tasks[task_id]
                        cls._current_task_id = task_id
                        
                        # 更新任务状态
                        task.status = TaskStatus.WAITING
                        task.message = "等待其他任务完成..."
                    
                    # 等待当前同步完成
                    max_wait = 300  # 最多等待5分钟
                    wait_start = time.time()
                    
                    while time.time() - wait_start < max_wait:
                        with cls._sync_lock:
                            if not cls._is_syncing:
                                break
                        time.sleep(2)
                    
                    # 执行任务
                    with cls._sync_lock:
                        cls._is_syncing = True
                        cls._last_sync_time = datetime.now()
                    
                    # 更新任务状态为运行中
                    with cls._task_lock:
                        task.status = TaskStatus.RUNNING
                        task.started_at = datetime.now()
                        task.message = "开始同步..."
                    
                    # 执行同步
                    try:
                        db = db_factory()
                        service = cls(db)
                        
                        # 自定义进度回调
                        def progress_callback(progress: int, message: str):
                            with cls._task_lock:
                                if task_id in cls._tasks:
                                    cls._tasks[task_id].progress = progress
                                    cls._tasks[task_id].message = message
                        
                        result = service.sync_with_limit(
                            is_auto_sync=task.is_auto_sync,
                            progress_callback=progress_callback
                        )
                        
                        # 更新任务完成状态
                        with cls._task_lock:
                            task.status = TaskStatus.COMPLETED
                            task.completed_at = datetime.now()
                            task.progress = 100
                            task.message = "同步完成"
                            task.result = result
                            
                    except Exception as e:
                        logger.error(f"Task {task_id} failed: {e}")
                        with cls._task_lock:
                            task.status = TaskStatus.FAILED
                            task.completed_at = datetime.now()
                            task.error = str(e)
                            task.message = f"同步失败: {str(e)}"
                    finally:
                        db.close()
                        with cls._sync_lock:
                            cls._is_syncing = False
                        cls._current_task_id = None
                        
                        # 更新队列中其他任务的位置
                        cls._update_queue_positions()
                        
                except Exception as e:
                    logger.error(f"Queue processor error: {e}")
                    time.sleep(5)
        
        cls._queue_processor_thread = threading.Thread(target=process_queue, daemon=True)
        cls._queue_processor_thread.start()
        cls._queue_processor_started = True
        logger.info("✅ 任务队列处理器已启动")

    @classmethod
    def _update_queue_positions(cls):
        """更新队列中所有任务的位置"""
        with cls._task_lock:
            # 获取当前队列中的所有任务
            queue_items = list(cls._task_queue.queue)
            for idx, task_id in enumerate(queue_items):
                if task_id in cls._tasks:
                    cls._tasks[task_id].queue_position = idx + 1
                    cls._tasks[task_id].message = f"等待中 (队列位置: {idx + 1})"

    @classmethod
    def create_sync_task(cls, db_factory, is_auto_sync: bool = False) -> str:
        """创建同步任务，返回任务ID"""
        
        # 确保队列处理器在运行
        cls._ensure_queue_processor(db_factory)
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 创建任务
        with cls._task_lock:
            task = SyncTask(task_id, is_auto_sync)
            
            # 检查是否已经有相同的任务在运行
            if cls._is_syncing and cls._current_task_id:
                # 检查当前运行的任务是否是相同的类型
                current_task = cls._tasks.get(cls._current_task_id)
                if current_task and current_task.is_auto_sync == is_auto_sync:
                    # 相同类型的任务，返回现有任务ID
                    return cls._current_task_id
            
            # 添加到任务列表
            cls._tasks[task_id] = task
            
            # 添加到队列
            cls._task_queue.put(task_id)
            
            # 更新队列位置
            queue_size = cls._task_queue.qsize()
            task.queue_position = queue_size
            task.message = f"等待中 (队列位置: {queue_size})"
            
        logger.info(f"📋 创建同步任务: {task_id}, 队列位置: {cls._task_queue.qsize()}")
        
        return task_id

    @classmethod
    def get_task_status(cls, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        with cls._task_lock:
            if task_id not in cls._tasks:
                return None
            
            task = cls._tasks[task_id]
            
            # 获取请求统计
            stats = GithubFetcher.get_request_stats() if task.status == TaskStatus.RUNNING else None
            
            return {
                "task_id": task.task_id,
                "status": task.status.value,
                "progress": task.progress,
                "message": task.message,
                "queue_position": task.queue_position,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "is_completed": task.status == TaskStatus.COMPLETED,
                "is_failed": task.status == TaskStatus.FAILED,
                "is_running": task.status == TaskStatus.RUNNING,
                "is_queued": task.status == TaskStatus.QUEUED or task.status == TaskStatus.WAITING,
                "result": task.result,
                "error": task.error,
                "api_stats": stats
            }

    @classmethod
    def get_all_tasks(cls, limit: int = 10) -> List[Dict]:
        """获取所有任务列表"""
        with cls._task_lock:
            tasks = list(cls._tasks.values())
            # 按创建时间倒序排序
            tasks.sort(key=lambda x: x.created_at, reverse=True)
            # 返回最近的limit个任务
            return [cls.get_task_status(t.task_id) for t in tasks[:limit]]

    @classmethod
    def get_queue_info(cls) -> Dict:
        """获取队列信息"""
        with cls._task_lock:
            return {
                "queue_size": cls._task_queue.qsize(),
                "is_processing": cls._is_syncing,
                "current_task_id": cls._current_task_id,
                "total_tasks": len(cls._tasks)
            }

    def sync_with_limit(self, is_auto_sync: bool = False, progress_callback=None):
        """同步方法 - 支持进度回调"""
        try:
            start_time = time.time()
            sync_type = "AUTO" if is_auto_sync else "MANUAL"
            
            target_items = min(1000 if is_auto_sync else self.MAX_ITEMS, self.MAX_ITEMS)
            
            logger.info(f"🚀 开始 {sync_type} 同步 (目标: {target_items} 条)")
            
            if progress_callback:
                progress_callback(5, f"开始{sync_type}同步...")

            # 重置请求计数
            GithubFetcher.start_session()
            
            if progress_callback:
                progress_callback(10, "重置请求计数器...")
            
            all_data = []
            page = 1
            max_pages = 5 if is_auto_sync else 10
            consecutive_empty = 0

            keywords = self.fetcher.keywords

            # 第一阶段：快速收集所有仓库
            logger.info("📚 第一阶段：收集仓库列表...")
            if progress_callback:
                progress_callback(15, "第一阶段：收集仓库列表...")
                
            all_repos = []
            
            while len(all_repos) < target_items * 3 and page <= max_pages:
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
                        page_repos.extend(repos[:15])

                if page_repos:
                    all_repos.extend(page_repos)
                    consecutive_empty = 0
                    
                    stats = GithubFetcher.get_request_stats()
                    progress = 15 + min(25, int((len(all_repos) / (target_items * 3)) * 25))
                    if progress_callback:
                        progress_callback(progress, f"收集仓库: 已收集 {len(all_repos)} 个仓库")
                    
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
            if progress_callback:
                progress_callback(40, "第二阶段：去重并获取仓库详情...")
            
            # 去重
            unique_repos = {}
            for repo in all_repos:
                repo_id = repo['id']
                if repo_id not in unique_repos:
                    unique_repos[repo_id] = repo
            
            repos_to_fetch = list(unique_repos.values())[:target_items * 2]
            logger.info(f"📊 去重后剩余 {len(repos_to_fetch)} 个唯一仓库")

            # 批量获取详情
            details = self.fetcher.fetch_repo_details_batch(repos_to_fetch)
            
            # 去重
            for idx, detail in enumerate(details):
                if detail and detail['name'] not in self.processed_repos:
                    all_data.append(detail)
                    self.processed_repos.add(detail['name'])
                    
                    if idx % 10 == 0 and progress_callback:
                        progress = 40 + min(30, int((len(all_data) / target_items) * 30))
                        progress_callback(progress, f"获取详情: 已处理 {len(all_data)}/{target_items} 条")
                    
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
            if progress_callback:
                progress_callback(70, "第三阶段：计算评分并保存到数据库...")
                
            result = self._process_and_save_data(all_data)
            
            stats = GithubFetcher.get_request_stats()
            result["api_stats"] = stats

            elapsed_time = time.time() - start_time
            result["elapsed_seconds"] = round(elapsed_time, 2)
            result["sync_type"] = sync_type

            if progress_callback:
                progress_callback(100, f"同步完成! 新增: {result.get('inserted', 0)}, 更新: {result.get('updated', 0)}")

            logger.info(f"✅ 同步完成: +{result.get('inserted', 0)} 新, "
                       f"{result.get('updated', 0)} 更新, 耗时 {elapsed_time:.1f}秒")

            return result

        except Exception as e:
            logger.error(f"同步错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            if progress_callback:
                progress_callback(0, f"同步失败: {str(e)}")
            return {"error": str(e), "message": "同步失败"}

    def _process_and_save_data(self, all_data):
        """处理和保存数据"""
        try:
            logger.info(f"处理 {len(all_data)} 条数据...")
            
            scored_data = Scorer(all_data).calculate()
            allowed_fields = Skill.__table__.columns.keys()

            updated_count = 0
            inserted_count = 0

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

                    if should_sync:
                        logger.info("创建自动同步任务...")
                        # 创建自动同步任务
                        cls.create_sync_task(db_factory, is_auto_sync=True)

                    sleep_time = 300 if consecutive_failures > 3 else 120
                    time.sleep(sleep_time)

                except Exception as e:
                    logger.error(f"Auto sync error: {e}")
                    time.sleep(300)

        cls._sync_task = threading.Thread(target=sync_worker, daemon=True)
        cls._sync_task.start()
        logger.info("Auto sync started")