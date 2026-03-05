from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings
import os

# 获取数据库连接字符串
database_url = settings.database_url

# 如果是SQLite，改为PostgreSQL（Neon）
if database_url.startswith('sqlite'):
    # 生产环境使用环境变量中的DATABASE_URL
    database_url = os.getenv('DATABASE_URL', database_url)
    # Neon需要SSL
    if 'neon.tech' in database_url:
        connect_args = {"sslmode": "require"}
    else:
        connect_args = {}
else:
    connect_args = {"sslmode": "require"} if 'neon.tech' in database_url else {}

engine = create_engine(
    database_url,
    connect_args=connect_args,
    pool_size=5,
    max_overflow=10
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()