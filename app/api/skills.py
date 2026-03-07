from fastapi import APIRouter, Depends, Query, HTTPException
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

        # 分类过滤
        if category:
            query = query.filter(Skill.category == category)

        # 排序逻辑
        if sort == "score":
            query = query.order_by(Skill.score.desc())
        elif sort == "stars":
            query = query.order_by(Skill.stars.desc())
        elif sort == "forks":
            query = query.order_by(Skill.forks.desc())
        elif sort == "time":
            query = query.order_by(Skill.last_commit.desc())

        # 统计总数
        total = query.count()

        # 分页
        items = query.offset((page - 1) * size).limit(size).all()

        return {
            "total": total,
            "items": items
        }

    except Exception as e:
        logger.error(f"Error in list_skills: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync/status")
def get_sync_status():
    """获取同步状态"""
    try:
        time_since = None
        if SyncService._last_sync_time:
            time_since = (datetime.now() - SyncService._last_sync_time).total_seconds() / 60

        return {
            "is_syncing": SyncService._is_syncing,
            "last_sync_time": SyncService._last_sync_time.isoformat() if SyncService._last_sync_time else None,
            "max_items": SyncService.MAX_ITEMS,
            "time_since_last_sync_minutes": round(time_since, 1) if time_since else None
        }
    except Exception as e:
        logger.error(f"Error getting sync status: {e}")
        return {"error": str(e)}


@router.get("/sync/progress")
def get_sync_progress():
    """获取同步进度"""
    try:
        stats = GithubFetcher.get_request_stats()

        return {
            "is_syncing": SyncService._is_syncing,
            "progress": stats,
            "last_sync": SyncService._last_sync_time.isoformat()
            if SyncService._last_sync_time else None
        }

    except Exception as e:
        logger.error(f"Error getting sync progress: {e}")
        return {"error": str(e)}


@router.post("/sync")
def sync_data(db: Session = Depends(get_db)):
    """手动触发同步"""
    try:
        logger.info("=" * 50)
        logger.info("MANUAL SYNC REQUESTED")
        logger.info("=" * 50)

        # 检查是否正在同步
        if SyncService._is_syncing:
            logger.warning("Manual sync blocked - sync already in progress")
            return {
                "message": "Sync already in progress",
                "status": "busy"
            }

        # 执行同步
        sync_service = SyncService(db)
        result = sync_service.sync_with_limit(is_auto_sync=False)

        logger.info("=" * 50)
        logger.info(f"MANUAL SYNC COMPLETED: {result}")
        logger.info("=" * 50)

        return result

    except Exception as e:
        logger.error(f"Error in sync_data: {str(e)}")
        logger.error(traceback.format_exc())
        return {"error": str(e), "message": "Sync failed"}


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
            "github_token_configured": bool(settings.github_token)
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