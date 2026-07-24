from __future__ import annotations

from pathlib import Path
from typing import AbstractSet

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.core.database import engine


BACKEND_ROOT = Path(__file__).resolve().parents[2]
BASELINE_REVISION = "0001_initial"
BASELINE_TABLES = frozenset(
    {
        "projects",
        "source_documents",
        "ai_tasks",
        "lesson_artifacts",
        "artifact_versions",
        "graph_runs",
        "export_jobs",
    }
)


def legacy_revision_to_stamp(
    table_names: AbstractSet[str],
    current_revision: str | None,
) -> str | None:
    """Return the baseline revision only for a complete, unversioned legacy schema."""
    if current_revision is not None:
        return None
    application_tables = set(table_names) - {"alembic_version"}
    baseline_tables = application_tables & BASELINE_TABLES
    if not baseline_tables:
        return None
    missing = sorted(BASELINE_TABLES - application_tables)
    if missing:
        raise RuntimeError(
            "数据库包含不完整的旧版表结构，无法安全自动登记迁移版本；"
            f"缺少表：{', '.join(missing)}"
        )
    return BASELINE_REVISION


def _alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("prepend_sys_path", str(BACKEND_ROOT))
    return config


def prepare_database(db_engine: Engine = engine) -> None:
    """Adopt a complete legacy schema, then apply all pending Alembic migrations."""
    with db_engine.connect() as connection:
        table_names = set(inspect(connection).get_table_names())
        current_revision = MigrationContext.configure(connection).get_current_revision()

    config = _alembic_config()
    revision = legacy_revision_to_stamp(table_names, current_revision)
    if revision:
        print(f"Detected legacy database; recording baseline {revision}.")
        command.stamp(config, revision)
    command.upgrade(config, "head")
    print("Database migrations are up to date.")


if __name__ == "__main__":
    prepare_database()
