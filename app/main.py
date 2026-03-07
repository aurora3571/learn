from fastapi import FastAPI
from app.database import Base, engine, SessionLocal
from app.api.skills import router
from sqlalchemy import text
import os
from app.services.sync_service import SyncService
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建FastAPI实例 - 这必须是顶级变量，Vercel需要找到名为'app'的变量
app = FastAPI(title="Agent Skills Platform")

# 包含路由 - 所有API路径都会加上/api前缀
app.include_router(router, prefix="/api")


@app.on_event("startup")
def startup_event():
    """应用启动时创建数据库表并启动自动同步"""
    logger.info("Creating database tables if not exist...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables check completed")

    # 启动自动同步（仅在非Vercel环境或生产环境）
    if os.getenv("ENVIRONMENT") != "vercel" or os.getenv("ENABLE_AUTO_SYNC") == "true":
        try:
            logger.info("Starting auto sync service...")
            SyncService.start_auto_sync(SessionLocal)
            logger.info("Auto sync service started successfully")
        except Exception as e:
            logger.error(f"Failed to start auto sync service: {e}")


@app.get("/")
def root():
    return {"message": "Agent Skills API Running"}


@app.get("/health")
def health_check():
    """健康检查"""
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()

        # 获取同步状态
        sync_status = {
            "is_syncing": SyncService._is_syncing,
            "last_sync_time": SyncService._last_sync_time.isoformat() if SyncService._last_sync_time else None
        }

        return {
            "status": "healthy",
            "database": "connected",
            "sync": sync_status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}