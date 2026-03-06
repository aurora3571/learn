from fastapi import FastAPI
from app.database import Base, engine
from app.api.skills import router
from sqlalchemy import text
import os

# 创建FastAPI实例 - 这必须是顶级变量，Vercel需要找到名为'app'的变量
app = FastAPI(title="Agent Skills Platform")

# 包含路由 - 所有API路径都会加上/api前缀
app.include_router(router, prefix="/api")

@app.on_event("startup")
def startup_event():
    """应用启动时创建数据库表"""
    print("Creating database tables if not exist...")
    Base.metadata.create_all(bind=engine)
    print("Database tables check completed")

@app.get("/")
def root():
    return {"message": "Agent Skills API Running"}

@app.get("/health")
def health_check():
    """健康检查"""
    try:
        from app.database import SessionLocal
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}