from pydantic import BaseSettings


class Settings(BaseSettings):
    github_token: str
    database_url: str

    class Config:
        env_file = ".env"


settings = Settings()