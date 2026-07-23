from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
import re

import pytest


ROOT = Path.cwd()
TMP_ROOT = ROOT / ".pytest-temp" / f"run-{os.getpid()}"
if TMP_ROOT.exists():
    shutil.rmtree(TMP_ROOT, ignore_errors=True)
TMP_ROOT.mkdir(parents=True, exist_ok=True)

for name in ("TMPDIR", "TEMP", "TMP"):
    os.environ.setdefault(name, str(TMP_ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DEEPSEEK_API_KEY", " ")
os.environ.setdefault("CHROMA_PERSIST_DIR", str(TMP_ROOT / "chroma"))
os.environ.setdefault("UPLOAD_DIR", str(TMP_ROOT / "uploads"))
os.environ.setdefault("EXPORT_DIR", str(TMP_ROOT / "exports"))
tempfile.tempdir = str(TMP_ROOT)


class SimpleTmpPathFactory:
    def __init__(self, base: Path):
        self.base = base
        self.base.mkdir(parents=True, exist_ok=True)
        self.counter = 0

    def getbasetemp(self) -> Path:
        return self.base

    def mktemp(self, basename: str, numbered: bool = True) -> Path:
        self.counter += 1
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", basename).strip("._") or "tmp"
        suffix = f"-{self.counter}" if numbered else ""
        path = self.base / f"{safe}{suffix}"
        path.mkdir(parents=True, exist_ok=False)
        return path


@pytest.fixture(scope="session")
def tmp_path_factory():
    return SimpleTmpPathFactory(TMP_ROOT / "tmp")


@pytest.fixture()
def tmp_path(tmp_path_factory, request):
    path = tmp_path_factory.mktemp(request.node.name[:48])
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def prepare_backend_environment():
    from app.core.database import Base, engine

    import app.models  # noqa: F401

    for path in (TMP_ROOT / "chroma", TMP_ROOT / "uploads", TMP_ROOT / "exports"):
        path.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def db_session():
    from app.core.database import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
