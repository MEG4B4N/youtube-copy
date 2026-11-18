from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "StreamHub"
    app_env: str = "development"
    app_secret_key: str = "dev-only-change-me-before-deploying"
    access_token_expire_minutes: int = 60 * 24 * 7
    cookie_secure: bool = False
    database_url: str = "sqlite:///./streamhub.db"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket: str = "streamhub-media"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    max_upload_bytes: int = 2 * 1024 * 1024 * 1024
    allowed_video_extensions: str = ".mp4,.mov,.mkv,.webm"

    @property
    def allowed_extensions(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_video_extensions.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
