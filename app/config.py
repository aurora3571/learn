from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    github_token: str
    database_url: str
    environment: Optional[str] = "development"
    enable_auto_sync: Optional[bool] = True  # 是否启用自动同步
    max_sync_items: Optional[int] = 4500  # 最大同步数量
    sync_interval_hours: Optional[int] = 1  # 同步间隔（小时）
    github_max_workers: Optional[int] = 10  # 并发工作线程数

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'


settings = Settings()