from fastapi import FastAPI
from app.database import Base, engine
from app.api.skills import router
from sqlalchemy import text  # 导入 text
import os

app = FastAPI(title="Agent Skills Platform")

app.include_router(router, prefix="/api")

@app.post("/init-db")
def init_database():
    """初始化数据库表"""
    try:
        Base.metadata.create_all(bind=engine)
        return {"message": "Database initialized successfully"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/health")
def health_check():
    """检查数据库连接"""
    try:
        from app.database import SessionLocal
        db = SessionLocal()
        db.execute(text("SELECT 1"))  # 修改这一行
        db.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}

@app.get("/")
def root():
    return {"message": "Agent Skills API Running"}