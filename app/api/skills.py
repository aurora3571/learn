from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import SessionLocal
from app.models import Skill
from app.schemas import SkillListResponse
from app.services.sync_service import SyncService
from app.services.github_fetcher import GithubFetcher
from app.config import settings

import logging
import traceback
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/skills", response_model=SkillListResponse)
def list_skills(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    sort: str = Query("score", regex="^(score|stars|forks|time)$"),
    category: str | None = Query(None),
    db: Session = Depends(get_db)
):
    """获取技能列表，支持分页、排序和分类过滤"""
    try:
        query = db.query(Skill)

        if category:
            query = query.filter(Skill.category == category)

        if sort == "score":
            query = query.order_by(Skill.score.desc())
        elif sort == "stars":
            query = query.order_by(Skill.stars.desc())
        elif sort == "forks":
            query = query.order_by(Skill.forks.desc())
        elif sort == "time":
            query = query.order_by(Skill.last_commit.desc())

        total = query.count()
        items = query.offset((page - 1) * size).limit(size).all()

        return {
            "total": total,
            "items": items
        }

    except Exception as e:
        logger.error(f"Error in list_skills: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
def sync_data(db: Session = Depends(get_db)):
    """手动触发同步 - 使用任务队列"""
    try:
        logger.info("=" * 50)
        logger.info("MANUAL SYNC REQUESTED")
        logger.info("=" * 50)

        # 创建同步任务
        task_id = SyncService.create_sync_task(
            db_factory=lambda: SessionLocal(),
            is_auto_sync=False
        )

        # 获取任务状态
        task_status = SyncService.get_task_status(task_id)
        
        # 获取队列信息
        queue_info = SyncService.get_queue_info()

        return {
            "message": "同步任务已创建",
            "status": "task_created",
            "task_id": task_id,
            "queue_position": task_status.get("queue_position") if task_status else None,
            "queue_size": queue_info.get("queue_size"),
            "is_processing": queue_info.get("is_processing"),
            "current_task_id": queue_info.get("current_task_id")
        }

    except Exception as e:
        logger.error(f"Error in sync_data: {str(e)}")
        logger.error(traceback.format_exc())
        return {"error": str(e), "message": "创建同步任务失败"}


@router.get("/sync/task/{task_id}")
def get_task_status(task_id: str):
    """获取特定同步任务的状态"""
    try:
        task_status = SyncService.get_task_status(task_id)
        
        if not task_status:
            return {"error": "Task not found", "task_id": task_id}
        
        return task_status
        
    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        return {"error": str(e)}


@router.get("/sync/tasks")
def list_tasks(limit: int = Query(10, ge=1, le=50)):
    """获取最近的任务列表"""
    try:
        tasks = SyncService.get_all_tasks(limit=limit)
        return {
            "tasks": tasks,
            "total": len(tasks)
        }
    except Exception as e:
        logger.error(f"Error listing tasks: {e}")
        return {"error": str(e)}


@router.get("/sync/queue")
def get_queue_info():
    """获取队列信息"""
    try:
        queue_info = SyncService.get_queue_info()
        
        # 获取当前运行任务的信息
        current_task = None
        if queue_info.get("current_task_id"):
            current_task = SyncService.get_task_status(queue_info["current_task_id"])
        
        return {
            "queue_size": queue_info.get("queue_size"),
            "is_processing": queue_info.get("is_processing"),
            "current_task": current_task,
            "total_tasks": queue_info.get("total_tasks")
        }
    except Exception as e:
        logger.error(f"Error getting queue info: {e}")
        return {"error": str(e)}


@router.get("/sync/status")
def get_sync_status():
    """获取同步状态（兼容旧版）"""
    try:
        queue_info = SyncService.get_queue_info()
        
        # 获取当前运行任务的信息
        current_task = None
        if queue_info.get("current_task_id"):
            current_task = SyncService.get_task_status(queue_info["current_task_id"])
        
        # 获取请求统计
        stats = GithubFetcher.get_request_stats()
        
        return {
            "is_syncing": queue_info.get("is_processing", False),
            "queue_size": queue_info.get("queue_size", 0),
            "current_task_id": queue_info.get("current_task_id"),
            "last_sync_time": SyncService._last_sync_time.isoformat() if SyncService._last_sync_time else None,
            "max_items": SyncService.MAX_ITEMS,
            "progress": stats if queue_info.get("is_processing") else None
        }
    except Exception as e:
        logger.error(f"Error getting sync status: {e}")
        return {"error": str(e)}


@router.get("/sync/progress")
def get_sync_progress():
    """获取当前同步进度（兼容旧版）"""
    try:
        stats = GithubFetcher.get_request_stats()
        queue_info = SyncService.get_queue_info()

        return {
            "is_syncing": queue_info.get("is_processing", False),
            "progress": stats,
            "last_sync": SyncService._last_sync_time.isoformat() if SyncService._last_sync_time else None,
            "queue_size": queue_info.get("queue_size", 0)
        }

    except Exception as e:
        logger.error(f"Error getting sync progress: {e}")
        return {"error": str(e)}


@router.get("/debug/sync-info")
def debug_sync_info(db: Session = Depends(get_db)):
    """调试信息：查看数据库状态"""
    try:
        total_skills = db.query(Skill).count()

        latest_skills = db.query(Skill).order_by(
            Skill.last_commit.desc()
        ).limit(5).all()

        categories = db.query(
            Skill.category,
            func.count(Skill.id)
        ).group_by(Skill.category).all()

        fetcher = GithubFetcher()
        
        # 获取队列信息
        queue_info = SyncService.get_queue_info()

        return {
            "database": {
                "total_records": total_skills,
                "categories": [
                    {"name": c[0], "count": c[1]}
                    for c in categories
                ],
                "latest_skills": [
                    {
                        "name": s.name,
                        "stars": s.stars,
                        "score": s.score,
                        "category": s.category
                    }
                    for s in latest_skills
                ]
            },
            "keywords": fetcher.keywords,
            "github_token_configured": bool(settings.github_token),
            "sync_queue": queue_info
        }

    except Exception as e:
        logger.error(f"Debug error: {e}")
        return {"error": str(e)}

@router.get("/debug/check-token")
def check_token():
    """检查 GitHub Token 是否有效"""
    try:
        from app.services.github_fetcher import GithubFetcher
        fetcher = GithubFetcher()
        
        # 测试 rate_limit API
        url = "https://api.github.com/rate_limit"
        response = fetcher._request(url)
        
        if response:
            data = response.json()
            rate = data.get('rate', {})
            return {
                "token_valid": True,
                "remaining_requests": rate.get('remaining', 0),
                "reset_time": rate.get('reset', 0),
                "token_preview": settings.github_token[:10] + "..." if settings.github_token else None
            }
        else:
            return {
                "token_valid": False,
                "error": "Failed to get rate limit"
            }
    except Exception as e:
        return {
            "token_valid": False,
            "error": str(e)
        }