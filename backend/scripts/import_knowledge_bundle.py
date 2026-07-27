from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import KnowledgeBase, SourceDocument


BUNDLE_VERSION = 1
EXPECTED_IDS = {
    "official-chinese",
    "official-mathematics",
    "official-english",
    "personal",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksum(bundle: Path) -> None:
    checksum_path = Path(f"{bundle}.sha256")
    if not checksum_path.is_file():
        print("警告：没有找到 .sha256 校验文件，将继续检查归档结构。", flush=True)
        return
    expected = checksum_path.read_text("utf-8").strip().split()[0]
    actual = sha256_file(bundle)
    if expected != actual:
        raise SystemExit("迁移包 SHA-256 校验失败，文件可能不完整或已损坏")
    print("SHA-256 校验通过。", flush=True)


def safe_extract(archive: tarfile.TarFile, target: Path) -> None:
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise SystemExit(f"迁移包包含不安全路径：{member.name}")
    archive.extractall(target, filter="data")


def parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.utcnow()
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def restore_database(manifest: dict, personal_root: Path) -> None:
    libraries = manifest["knowledge_bases"]
    sources = manifest.get("personal_sources", [])
    with SessionLocal() as db:
        try:
            db.query(SourceDocument).filter(
                SourceDocument.knowledge_base_id == "personal"
            ).delete(synchronize_session=False)
            for row in libraries:
                item = db.get(KnowledgeBase, row["id"])
                if not item:
                    item = KnowledgeBase(id=row["id"])
                    db.add(item)
                for field in (
                    "name",
                    "kind",
                    "subject",
                    "description",
                    "status",
                    "read_only",
                    "document_count",
                    "chunk_count",
                    "size_bytes",
                    "error_message",
                ):
                    setattr(item, field, row.get(field))
            db.flush()
            for row in sources:
                stored_name = Path(row["stored_name"]).name
                stored_path = personal_root / stored_name
                if row["status"] == "ready" and not stored_path.is_file():
                    raise RuntimeError(f"个人资料文件缺失：{stored_name}")
                db.add(
                    SourceDocument(
                        id=row["id"],
                        project_id=None,
                        knowledge_base_id="personal",
                        original_name=row["original_name"],
                        stored_name=stored_name,
                        media_type=row["media_type"],
                        size=row["size"],
                        sha256=row["sha256"],
                        storage_path=str(stored_path),
                        status=row["status"],
                        error_message=row.get("error_message"),
                        created_at=parse_time(row.get("created_at")),
                        updated_at=parse_time(row.get("updated_at")),
                    )
                )
            db.commit()
        except Exception:
            db.rollback()
            raise


def import_bundle(bundle: Path, replace: bool) -> None:
    if not replace:
        raise SystemExit("导入会替换当前知识库；确认目标实例无须保留旧知识库后，请添加 --replace")
    bundle = bundle.resolve()
    if not bundle.is_file():
        raise SystemExit(f"迁移包不存在：{bundle}")
    verify_checksum(bundle)

    settings = get_settings()
    data_root = settings.chroma_persist_dir.resolve().parent
    data_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".knowledge-import-", dir=data_root))
    chroma_target = settings.chroma_persist_dir.resolve()
    personal_target = (settings.upload_dir / "personal").resolve()
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    chroma_backup = chroma_target.with_name(f"{chroma_target.name}.backup-{stamp}")
    personal_backup = personal_target.with_name(f"{personal_target.name}.backup-{stamp}")
    moved_chroma = False
    moved_personal = False
    installed_chroma = False
    installed_personal = False

    try:
        print("正在解压并检查迁移包……", flush=True)
        with tarfile.open(bundle, mode="r:*") as archive:
            safe_extract(archive, staging)
        manifest_path = staging / "manifest.json"
        imported_chroma = staging / "chroma"
        imported_personal = staging / "uploads" / "personal"
        if not manifest_path.is_file() or not (imported_chroma / "chroma.sqlite3").is_file():
            raise RuntimeError("迁移包缺少 manifest.json 或 Chroma 数据")
        manifest = json.loads(manifest_path.read_text("utf-8"))
        if manifest.get("bundle_version") != BUNDLE_VERSION:
            raise RuntimeError(f"不支持的迁移包版本：{manifest.get('bundle_version')}")
        if set(manifest.get("knowledge_base_ids", [])) != EXPECTED_IDS:
            raise RuntimeError("迁移包不是完整的 Any2PPT 四知识库")

        if chroma_backup.exists() or personal_backup.exists():
            raise RuntimeError("检测到同名备份目录，请先人工确认后再导入")
        if chroma_target.exists():
            chroma_target.rename(chroma_backup)
            moved_chroma = True
        imported_chroma.rename(chroma_target)
        installed_chroma = True

        personal_target.parent.mkdir(parents=True, exist_ok=True)
        if personal_target.exists():
            personal_target.rename(personal_backup)
            moved_personal = True
        if imported_personal.exists():
            imported_personal.rename(personal_target)
        else:
            personal_target.mkdir(parents=True, exist_ok=True)
        installed_personal = True

        restore_database(manifest, personal_target)
        if moved_chroma:
            shutil.rmtree(chroma_backup, ignore_errors=True)
        if moved_personal:
            shutil.rmtree(personal_backup, ignore_errors=True)
        print("知识库导入完成。现在可以启动完整 Docker 服务。", flush=True)
    except Exception:
        if installed_chroma and chroma_target.exists():
            shutil.rmtree(chroma_target, ignore_errors=True)
        if moved_chroma and chroma_backup.exists():
            chroma_backup.rename(chroma_target)
        if installed_personal and personal_target.exists():
            shutil.rmtree(personal_target, ignore_errors=True)
        if moved_personal and personal_backup.exists():
            personal_backup.rename(personal_target)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将 Any2PPT 知识库迁移包恢复到当前 Docker 数据卷")
    parser.add_argument("bundle", type=Path, help="位于 /app/transfer 中的 .tar.gz 文件")
    parser.add_argument("--replace", action="store_true", help="确认替换当前实例的知识库")
    args = parser.parse_args()
    import_bundle(args.bundle, args.replace)
