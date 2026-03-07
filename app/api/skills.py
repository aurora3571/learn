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


@router.get("/sync/progress")
def get_sync_progress():

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


@router.get("/debug/sync-info")
def debug_sync_info(db: Session = Depends(get_db)):

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