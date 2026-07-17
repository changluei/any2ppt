from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "面向智慧教育的 AI 备课辅助系统"
    environment: str = "development"
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_database: str = "lessondeck"
    mysql_user: str = "lessondeck"
    mysql_password: str = "change_me"
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
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    @property
    def database_url(self) -> str:
        from urllib.parse import quote_plus
        return f"mysql+pymysql://{quote_plus(self.mysql_user)}:{quote_plus(self.mysql_password)}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"


@lru_cache
def get_settings() -> Settings:
    return Settings()

