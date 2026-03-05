from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Skill
from app.schemas import SkillListResponse
from app.services.sync_service import SyncService

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/skills", response_model=SkillListResponse)
def list_skills(
    page: int = Query(1),
    size: int = Query(10),
    sort: str = Query("score"),
    category: str | None = Query(None),
    db: Session = Depends(get_db)
):

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


@router.get("/skills/category/{category}")
def by_category(category: str, db: Session = Depends(get_db)):
    return db.query(Skill).filter(Skill.category == category).all()


@router.post("/sync")
def sync_data(db: Session = Depends(get_db)):
    SyncService(db).sync()
    return {"message": "Sync completed"}