from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "backend"


class Settings(BaseSettings):
    app_name: str = "面向智慧教育的 AI 备课辅助系统"
    environment: str = "development"
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_database: str = "lessondeck"
    mysql_user: str = "lessondeck"
    mysql_password: str = "change_me"
    database_url_override: str | None = Field(default=None, validation_alias="DATABASE_URL")
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    ai_timeout_seconds: int = 60
    ai_temperature: float = 0.2
    chroma_persist_dir: Path = Path("data/chroma")
    upload_dir: Path = Path("data/uploads")
    export_dir: Path = Path("data/exports")
    max_upload_mb: int = 20
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_ROOT / ".env"), str(BACKEND_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        from urllib.parse import quote_plus

        return (
            "mysql+pymysql://"
            f"{quote_plus(self.mysql_user)}:{quote_plus(self.mysql_password)}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

