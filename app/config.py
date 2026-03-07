from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    github_token: str
    database_url: str
    environment: Optional[str] = "development"
    enable_auto_sync: Optional[bool] = True
    max_sync_items: Optional[int] = 5000
    sync_interval_hours: Optional[int] = 2  # 改为2小时
    github_max_workers: Optional[int] = 10  # 降低并发数
    request_timeout: Optional[int] = 15  # 增加超时时间
    batch_size: Optional[int] = 20  # 减小批处理大小

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'


settings = Settings()