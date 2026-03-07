from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    github_token: str
    database_url: str
    environment: Optional[str] = "development"
    enable_auto_sync: Optional[bool] = True
    max_sync_items: Optional[int] = 5000  # 最大同步数量
    sync_interval_hours: Optional[int] = 2  # 同步间隔（小时）
    
    # 并发控制（平衡值）
    github_max_workers: Optional[int] = 10  # 最大工作线程
    max_connections: Optional[int] = 50  # 最大连接数
    
    # 超时设置
    request_timeout: Optional[int] = 15  # 请求超时（秒）
    connect_timeout: Optional[int] = 10  # 连接超时（秒）
    read_timeout: Optional[int] = 15  # 读取超时（秒）
    
    # 批处理
    batch_size: Optional[int] = 20  # 批处理大小
    
    # 延迟控制
    request_delay: Optional[float] = 0.1  # 请求延迟（秒）
    max_retries: Optional[int] = 2  # 最大重试次数
    
    # 限流控制
    rate_limit_threshold: Optional[int] = 50  # 限流阈值
    rate_limit_sleep: Optional[int] = 60  # 限流等待时间（秒）

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'


settings = Settings()