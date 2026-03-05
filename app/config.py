from pydantic import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    github_token: str
    database_url: str
    environment: Optional[str] = "development"

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()