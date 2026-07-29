"""SQLAlchemy 引擎、声明式基类和请求级会话工厂。

生产环境使用 MySQL 连接池；测试允许 SQLite，且内存 SQLite 必须配合
StaticPool 才能让不同会话看到同一份数据。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import get_settings


class Base(DeclarativeBase):
    """所有 ORM 实体的共同声明式基类。"""
    pass


settings = get_settings()
engine_kwargs: dict[str, object] = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    if ":memory:" in settings.database_url or settings.database_url.rstrip("/") in {
        "sqlite:",
        "sqlite://",
    }:
        engine_kwargs["poolclass"] = StaticPool
else:
    engine_kwargs["pool_recycle"] = 1800

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI 依赖：每个请求获得独立 Session，并在响应后可靠关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
