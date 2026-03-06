from sqlalchemy import create_engine, text  # 导入 text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 获取数据库连接字符串
database_url = settings.database_url
logger.info(f"Connecting to database: {database_url[:20]}...")

try:
    # 配置连接参数
    connect_args = {}
    if 'neon.tech' in database_url:
        connect_args = {
            "sslmode": "require",
            "connect_timeout": 10
        }
    
    # 创建引擎
    engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True
    )
    
    # 测试连接 - 关键修改：使用 text()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))  # 修改这一行
        logger.info("✅ Database connected successfully!")
        
except Exception as e:
    logger.error(f"❌ Database connection failed: {str(e)}")
    engine = None

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None
Base = declarative_base()