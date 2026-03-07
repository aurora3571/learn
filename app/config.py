from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    github_token: str
    database_url: str
    environment: Optional[str] = "development"
    enable_auto_sync: Optional[bool] = True  # 是否启用自动同步
    max_sync_items: Optional[int] = 5000  # 从4500修改为5000
    sync_interval_hours: Optional[int] = 1  # 同步间隔（小时）
    github_max_workers: Optional[int] = 20  # 从10增加到20，提高并发
    request_timeout: Optional[int] = 10  # 请求超时时间（秒）
    batch_size: Optional[int] = 50  # 批量处理大小

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'


settings = Settings()