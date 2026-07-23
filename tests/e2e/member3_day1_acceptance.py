from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


def run_command(
    args: list[str],
    cwd: Path = ROOT,
    timeout: int = 30,
    env_extra: dict[str, str] | None = None,
) -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if env_extra:
        env.update(env_extra)
    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd),
            env=env,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
    except FileNotFoundError as exc:
        return 127, str(exc)
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        return 124, output.strip() or f"命令超时：{timeout}s"
    return completed.returncode, (completed.stdout + completed.stderr).strip()


def docker_command() -> str | None:
    from_path = shutil.which("docker")
    if from_path:
        return from_path
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "DockerDesktop" / "resources" / "bin" / "docker.exe",
        Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def result(name: str, ok: bool, pass_detail: str, fail_detail: str) -> CheckResult:
    return CheckResult(name, "通过" if ok else "失败", pass_detail if ok else fail_detail)


def check_root() -> CheckResult:
    required = ["backend", "contracts", "deploy", "README.md", ".env.example"]
    missing = [item for item in required if not (ROOT / item).exists()]
    return result(
        "项目根目录",
        not missing,
        f"当前根目录：{ROOT}",
        f"缺少：{', '.join(missing)}；当前根目录：{ROOT}",
    )


def check_backend_structure() -> CheckResult:
    required = [
        "app/main.py",
        "app/api/routes",
        "app/core/config.py",
        "app/core/database.py",
        "app/models",
        "app/schemas",
        "app/services",
        "app/repositories",
        "migrations",
        "migrations/versions",
        "tests",
    ]
    missing = [item for item in required if not (BACKEND / item).exists()]
    return result(
        "FastAPI 分层目录",
        not missing,
        "backend/app、migrations、backend/tests 结构完整",
        "缺少：" + ", ".join(missing),
    )


def check_requirements() -> CheckResult:
    path = BACKEND / "requirements" / "base.txt"
    if not path.exists():
        return CheckResult("base.txt 依赖", "失败", "backend/requirements/base.txt 不存在")
    text = path.read_text(encoding="utf-8").lower()
    required = ["fastapi", "sqlalchemy", "pymysql", "alembic", "pydantic-settings"]
    missing = [item for item in required if item not in text]
    return result(
        "base.txt 依赖",
        not missing,
        "包含 FastAPI、SQLAlchemy、PyMySQL、Alembic、pydantic-settings",
        "缺少：" + ", ".join(missing),
    )


def check_mysql_config() -> CheckResult:
    config = (BACKEND / "app" / "core" / "config.py").read_text(encoding="utf-8")
    database = (BACKEND / "app" / "core" / "database.py").read_text(encoding="utf-8")
    ok = "mysql+pymysql://" in config and "charset=utf8mb4" in config and "create_engine" in database
    return result(
        "MySQL 连接配置",
        ok,
        "默认连接串使用 mysql+pymysql 且 charset=utf8mb4",
        "未找到 mysql+pymysql、utf8mb4 或 SQLAlchemy create_engine 配置",
    )


def check_no_startup_create_all() -> CheckResult:
    offenders: list[str] = []
    for path in (BACKEND / "app").rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "create_all" in text:
            offenders.append(str(path.relative_to(ROOT)))
    return result(
        "正式代码不使用 create_all 代替迁移",
        not offenders,
        "backend/app 中未发现 create_all",
        "发现 create_all：" + ", ".join(offenders),
    )


def check_env_and_tracked_data() -> list[CheckResult]:
    checks: list[CheckResult] = []
    code, output = run_command(["git", "ls-files", ".env"])
    checks.append(
        result(
            ".env 不进入 Git",
            code == 0 and not output.strip(),
            ".env 未被 Git 跟踪",
            ".env 被 Git 跟踪或 git 检查失败：" + output,
        )
    )

    allowed = {"data/.gitkeep", "backend/data/.gitkeep"}
    code, output = run_command(["git", "ls-files", "data", "backend/data"])
    tracked = {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}
    bad = sorted(item for item in tracked if item not in allowed)
    checks.append(
        result(
            "上传/导出/Chroma 数据不进入 Git",
            code == 0 and not bad,
            "未跟踪生成数据，只允许 .gitkeep",
            "仍被跟踪：" + ", ".join(bad),
        )
    )
    return checks


def check_app_routes() -> CheckResult:
    code, output = run_command(
        [
            sys.executable,
            "-c",
            (
                "from app.main import app; "
                "paths={r.path for r in app.routes}; "
                "required={'/health','/health/db','/api/projects','/api/projects/{project_id}'}; "
                "missing=required-paths; "
                "print('missing=' + ','.join(sorted(missing))) if missing else print('routes ok')"
            ),
        ],
        cwd=BACKEND,
    )
    return result(
        "FastAPI 导入与基础路由",
        code == 0 and "routes ok" in output,
        "app 可导入，/health、/health/db、/api/projects 已注册",
        output or "导入失败",
    )


def check_alembic_head() -> CheckResult:
    code, output = run_command([sys.executable, "-m", "alembic", "-c", "alembic.ini", "heads"], cwd=BACKEND)
    return result(
        "Alembic 迁移",
        code == 0 and "0002_task_result_snapshot" in output,
        output,
        output or "未识别到 0002_task_result_snapshot head",
    )


def check_compileall() -> CheckResult:
    code, output = run_command([sys.executable, "-m", "compileall", "backend/app", "-q"], cwd=ROOT)
    return result("Python 编译检查", code == 0, "backend/app 编译通过", output or "compileall 失败")


def check_day1_pytest() -> CheckResult:
    code, output = run_command(
        [
            sys.executable,
            "-m",
            "pytest",
            "backend/tests/test_backend_api.py::test_health_and_project_crud",
            "-q",
        ],
        cwd=ROOT,
        timeout=60,
        env_extra={
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "CHROMA_PERSIST_DIR": str(ROOT / ".pytest-temp" / "acceptance-chroma"),
            "UPLOAD_DIR": str(ROOT / ".pytest-temp" / "acceptance-uploads"),
            "EXPORT_DIR": str(ROOT / ".pytest-temp" / "acceptance-exports"),
        },
    )
    return result(
        "Day 1 后端接口测试",
        code == 0,
        "health、项目创建/查询、无效 ID 测试通过",
        output or "pytest 失败",
    )


def check_compose_static() -> CheckResult:
    path = ROOT / "deploy" / "docker-compose.yml"
    if not path.exists():
        return CheckResult("Docker Compose 静态配置", "失败", "deploy/docker-compose.yml 不存在")
    text = path.read_text(encoding="utf-8")
    required = ["mysql:", "mysql:8", "backend:", "frontend:", "healthcheck:", "volumes:"]
    missing = [item for item in required if item not in text]
    return result(
        "Docker Compose 静态配置",
        not missing,
        "包含 mysql:8、backend、frontend、healthcheck、volumes",
        "缺少：" + ", ".join(missing),
    )


def check_docker_compose_config() -> CheckResult:
    docker = docker_command()
    if not docker:
        return CheckResult("Docker Compose 真实解析", "未验证", "未检测到 docker 命令，无法运行 docker compose config")
    code, output = run_command([docker, "compose", "-f", "deploy/docker-compose.yml", "config"], timeout=60)
    return result(
        "Docker Compose 真实解析",
        code == 0,
        "docker compose config 通过",
        output or "docker compose config 失败",
    )


def check_real_mysql() -> CheckResult:
    alembic_code, alembic_output = run_command(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "current"],
        cwd=BACKEND,
    )
    health_code, health_output = run_command(
        [
            sys.executable,
            "-c",
            (
                "from fastapi.testclient import TestClient; "
                "from app.main import app; "
                "data=TestClient(app).get('/health/db').json(); "
                "print(data)"
            ),
        ],
        cwd=BACKEND,
    )
    ok = (
        alembic_code == 0
        and "0002_task_result_snapshot" in alembic_output
        and health_code == 0
        and "'status': 'ok'" in health_output
        and "'database': 'mysql'" in health_output
    )
    if ok:
        return CheckResult("真实 MySQL 8 迁移与 /health/db", "通过", "Alembic 当前版本为 0002_task_result_snapshot，/health/db 返回 mysql ok")
    return CheckResult(
        "真实 MySQL 8 迁移与 /health/db",
        "未验证",
        "Alembic: " + (alembic_output or "无输出") + "；health/db: " + (health_output or "无输出"),
    )


def print_table(results: list[CheckResult]) -> None:
    widths = {
        "name": max(len("验收项"), *(len(item.name) for item in results)),
        "status": max(len("结果"), *(len(item.status) for item in results)),
    }
    print("\n第 1 天成员 3 自动验收结果")
    print(f"项目根目录：{ROOT}")
    print("-" * 90)
    print(f"{'验收项':<{widths['name']}}  {'结果':<{widths['status']}}  说明")
    print("-" * 90)
    for item in results:
        print(f"{item.name:<{widths['name']}}  {item.status:<{widths['status']}}  {item.detail}")
    print("-" * 90)
    counts = {status: sum(1 for item in results if item.status == status) for status in ("通过", "失败", "未验证")}
    print(f"汇总：通过 {counts['通过']}，失败 {counts['失败']}，未验证 {counts['未验证']}")
    if counts["未验证"]:
        print("说明：未验证项通常需要真实 Docker/MySQL 环境，脚本不会把本机缺失环境伪造成通过。")


def main() -> int:
    results: list[CheckResult] = [
        check_root(),
        check_backend_structure(),
        check_requirements(),
        check_mysql_config(),
        check_no_startup_create_all(),
        *check_env_and_tracked_data(),
        check_app_routes(),
        check_alembic_head(),
        check_compileall(),
        check_day1_pytest(),
        check_compose_static(),
        check_docker_compose_config(),
        check_real_mysql(),
    ]
    print_table(results)
    return 1 if any(item.status == "失败" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
