from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    github_token: str
    database_url: str
    environment: Optional[str] = "development"
    enable_auto_sync: Optional[bool] = True
    max_sync_items: Optional[int] = 5000  # 最大同步数量
    sync_interval_hours: Optional[int] = 1  # 同步间隔（小时）
    
    # 提高并发控制
    github_max_workers: Optional[int] = 20  # 增加最大工作线程
    max_connections: Optional[int] = 100  # 增加最大连接数
    
    # 减少超时设置
    request_timeout: Optional[int] = 10  # 减少请求超时
    connect_timeout: Optional[int] = 5  # 减少连接超时
    read_timeout: Optional[int] = 10  # 减少读取超时
    
    # 增大批处理
    batch_size: Optional[int] = 100  # 增大批处理大小
    
    # 减少延迟控制
    request_delay: Optional[float] = 0.05  # 减少请求延迟
    max_retries: Optional[int] = 1  # 减少最大重试次数
    
    # 限流控制
    rate_limit_threshold: Optional[int] = 50  # 限流阈值
    rate_limit_sleep: Optional[int] = 60  # 限流等待时间

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'


settings = Settings()