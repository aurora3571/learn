from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Skill
from app.schemas import SkillListResponse
from app.services.sync_service import SyncService
from app.config import settings
import traceback
import logging
from datetime import datetime

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
    """同步 GitHub 数据（手动触发）- 改进版"""
    try:
        logger.info("Starting manual sync process...")

        # 检查是否正在同步
        if SyncService._is_syncing:
            return {"message": "Sync already in progress", "status": "busy"}

        # 执行同步（非自动模式）
        sync_service = SyncService(db)
        result = sync_service.sync_with_limit(is_auto_sync=False)

        return result

    except Exception as e:
        logger.error(f"Error in sync_data: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": str(e), "message": "Sync failed"}


@router.get("/sync/status")
def get_sync_status():
    """获取当前同步状态"""
    try:
        time_since = None
        if SyncService._last_sync_time:
            time_since = (datetime.now() - SyncService._last_sync_time).total_seconds() / 60

        return {
            "is_syncing": SyncService._is_syncing,
            "last_sync_time": SyncService._last_sync_time.isoformat() if SyncService._last_sync_time else None,
            "max_items": SyncService.MAX_ITEMS,
            "time_since_last_sync_minutes": round(time_since, 1) if time_since else None,
            "auto_sync_enabled": True
        }
    except Exception as e:
        logger.error(f"Error getting sync status: {e}")
        return {"error": str(e)}


@router.get("/debug/sync-info")
def debug_sync_info(db: Session = Depends(get_db)):
    """调试端点：查看同步状态和数据情况"""
    try:
        # 1. 检查数据库中的记录数
        total_skills = db.query(Skill).count()

        # 2. 获取最新的几条记录
        latest_skills = db.query(Skill).order_by(Skill.last_commit.desc()).limit(5).all()

        # 3. 获取同步服务状态
        sync_status = {
            "is_syncing": SyncService._is_syncing,
            "last_sync_time": SyncService._last_sync_time.isoformat() if SyncService._last_sync_time else None,
        }

        # 4. 检查 GitHub token 是否有效（不显示完整 token）
        token_preview = settings.github_token[:10] + "..." if settings.github_token else "Not set"

        # 5. 统计分类
        categories = db.query(Skill.category, db.func.count(Skill.id)).group_by(Skill.category).all()

        return {
            "database": {
                "total_records": total_skills,
                "categories": [{"name": c[0], "count": c[1]} for c in categories],
                "latest_skills": [
                    {
                        "name": s.name,
                        "last_commit": s.last_commit.isoformat() if s.last_commit else None,
                        "stars": s.stars,
                        "score": s.score,
                        "category": s.category
                    } for s in latest_skills
                ]
            },
            "sync_service": sync_status,
            "github_token": token_preview,
            "max_items": SyncService.MAX_ITEMS,
            "keywords": GithubFetcher().keywords if hasattr(GithubFetcher, 'keywords') else []
        }
    except Exception as e:
        logger.error(f"Debug info error: {e}")
        return {"error": str(e)}


@router.get("/debug/sync-progress")
def debug_sync_progress():
    """查看当前同步进度"""
    try:
        return {
            "is_syncing": SyncService._is_syncing,
            "last_sync_time": SyncService._last_sync_time.isoformat() if SyncService._last_sync_time else None,
            "max_items": SyncService.MAX_ITEMS,
            "current_time": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}


@router.post("/sync/debug")
def debug_sync(db: Session = Depends(get_db)):
    """调试模式的同步，只抓取少量数据"""
    try:
        logger.info("Starting debug sync...")

        # 检查是否正在同步
        if SyncService._is_syncing:
            return {"message": "Sync already in progress", "status": "busy"}

        # 临时修改最大数量为50
        original_max = SyncService.MAX_ITEMS
        SyncService.MAX_ITEMS = 50

        sync_service = SyncService(db)
        result = sync_service.sync_with_limit(is_auto_sync=False)

        # 恢复原值
        SyncService.MAX_ITEMS = original_max

        return {
            "debug_mode": True,
            "result": result,
            "note": "只抓取了50条数据进行测试"
        }
    except Exception as e:
        logger.error(f"Debug sync error: {e}")
        return {"error": str(e)}


@router.post("/sync/test")
def test_sync_manual(db: Session = Depends(get_db)):
    """测试同步，返回抓取的数据而不保存"""
    try:
        from app.services.github_fetcher import GithubFetcher

        fetcher = GithubFetcher()
        test_keyword = "agent"

        # 测试搜索
        repos = fetcher.search(test_keyword, page=1, per_page=5)

        results = []
        for repo in repos[:3]:  # 只测试前3个
            details = fetcher.fetch_repo_details(repo)
            if details:
                results.append({
                    "name": details.get("name"),
                    "stars": details.get("stars"),
                    "forks": details.get("forks"),
                    "category": details.get("category"),
                    "description": details.get("description")[:100] + "..." if details.get("description") else "No description"
                })

        return {
            "test_keyword": test_keyword,
            "repos_found": len(repos),
            "sample_results": results,
            "github_token_preview": settings.github_token[:10] + "..." if settings.github_token else "Not set",
            "keywords": fetcher.keywords
        }
    except Exception as e:
        logger.error(f"Test sync error: {e}")
        return {"error": str(e)}


@router.get("/test-sync")
def test_sync():
    """测试同步服务是否可用的端点"""
    try:
        from app.services.sync_service import SyncService
        from app.database import SessionLocal
        from app.services.github_fetcher import GithubFetcher

        db = SessionLocal()
        try:
            # 创建实例但不执行同步
            service = SyncService(db)
            fetcher = GithubFetcher()

            # 检查方法
            methods = [method for method in dir(service) if not method.startswith('_')]

            return {
                "status": "success",
                "service_loaded": True,
                "has_sync_method": hasattr(service, "sync"),
                "has_sync_with_limit": hasattr(service, "sync_with_limit"),
                "available_methods": methods,
                "service_class": str(service.__class__),
                "module": service.__class__.__module__,
                "github_token_configured": bool(settings.github_token),
                "keywords_count": len(fetcher.keywords)
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