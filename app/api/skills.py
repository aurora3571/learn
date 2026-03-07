from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Skill
from app.schemas import SkillListResponse
from app.services.sync_service import SyncService
import traceback
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
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
        logger.error(f"Error in list_skills: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/skills/category/{category}")
def by_category(category: str, db: Session = Depends(get_db)):
    """根据分类获取技能"""
    try:
        return db.query(Skill).filter(Skill.category == category).all()
    except Exception as e:
        logger.error(f"Error in by_category: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
def sync_data(db: Session = Depends(get_db)):
    """同步 GitHub 数据（手动触发）"""
    try:
        logger.info("Starting manual sync process...")

        # 记录开始时间
        import time
        start_time = time.time()

        # 执行同步
        sync_service = SyncService(db)
        logger.info(f"SyncService instance created")

        # 执行同步
        result = sync_service.sync_with_limit()
        logger.info(f"Sync completed, result: {result}")

        return result

    except Exception as e:
        logger.error(f"Error in sync_data: {str(e)}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}


@router.get("/sync/status")
def get_sync_status():
    """获取当前同步状态"""
    return {
        "is_syncing": SyncService._is_syncing,
        "last_sync_time": SyncService._last_sync_time.isoformat() if SyncService._last_sync_time else None,
        "max_items": SyncService.MAX_ITEMS
    }


@router.get("/test-sync")
def test_sync():
    """测试同步服务是否可用的端点"""
    try:
        from app.services.sync_service import SyncService
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            # 创建实例但不执行同步
            service = SyncService(db)

            # 检查方法
            methods = [method for method in dir(service) if not method.startswith('_')]

            return {
                "status": "success",
                "service_loaded": True,
                "has_sync_method": hasattr(service, "sync"),
                "has_sync_with_limit": hasattr(service, "sync_with_limit"),
                "available_methods": methods,
                "service_class": str(service.__class__),
                "module": service.__class__.__module__
            }
        finally:
            db.close()
    except ImportError as e:
        return {
            "status": "error",
            "error_type": "import_error",
            "error": str(e)
        }
    except Exception as e:
        return {
            "status": "error",
            "error_type": "unknown",
            "error": str(e),
            "traceback": traceback.format_exc()
        }