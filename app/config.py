from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    github_token: str
    database_url: str
    environment: Optional[str] = "development"
    enable_auto_sync: Optional[bool] = True
    max_sync_items: Optional[int] = 5000
    sync_interval_hours: Optional[int] = 1
    github_max_workers: Optional[int] = 30
    request_timeout: Optional[int] = 10
    batch_size: Optional[int] = 50
    max_connections: Optional[int] = 200  # 添加这个配置项
    request_delay: Optional[float] = 0.1
    max_retries: Optional[int] = 2

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'


settings = Settings()