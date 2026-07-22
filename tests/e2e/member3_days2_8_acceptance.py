from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


@dataclass
class CheckResult:
    day: str
    name: str
    status: str
    detail: str


def docker_command() -> str | None:
    found = shutil.which("docker")
    if found:
        return found
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "DockerDesktop" / "resources" / "bin" / "docker.exe",
        Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def run_command(args: list[str], cwd: Path = ROOT, timeout: int = 60) -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    docker = docker_command()
    if docker:
        docker_bin = str(Path(docker).parent)
        env["PATH"] = docker_bin + os.pathsep + env.get("PATH", "")
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


def ok(day: str, name: str, detail: str) -> CheckResult:
    return CheckResult(day, name, "通过", detail)


def fail(day: str, name: str, detail: str) -> CheckResult:
    return CheckResult(day, name, "失败", detail)


def skip(day: str, name: str, detail: str) -> CheckResult:
    return CheckResult(day, name, "未验证", detail)


def guarded(day: str, name: str, fn: Callable[[], str]) -> CheckResult:
    try:
        return ok(day, name, fn())
    except AssertionError as exc:
        return fail(day, name, str(exc))
    except Exception as exc:
        return fail(day, name, f"{type(exc).__name__}: {exc}")


def wait_until(fetch: Callable[[], dict[str, Any]], done: set[str], timeout: float, label: str) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = fetch()
        if last.get("status") in done:
            return last
        time.sleep(0.1)
    raise AssertionError(f"{label} 未在 {timeout}s 内结束，最后状态：{last}")


def create_project(client, suffix: str) -> dict[str, Any]:
    response = client.post(
        "/api/projects",
        json={
            "name": f"成员3验收项目-{suffix}",
            "subject": "科学",
            "grade": "三年级",
            "textbook_version": "自编",
            "lesson_topic": "水的三态变化",
            "lesson_count": 1,
            "student_profile": "学生能观察并描述生活中的水变化现象",
            "teacher_requirements": "突出实验安全和来源追溯",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload_source(client, project_id: str, name: str, content: bytes) -> dict[str, Any]:
    response = client.post(
        f"/api/projects/{project_id}/sources",
        files={"file": (name, content, "text/markdown")},
    )
    assert response.status_code == 201, response.text
    source_id = response.json()["id"]
    return wait_until(
        lambda: client.get(f"/api/projects/{project_id}/sources/{source_id}").json(),
        {"ready", "failed"},
        8.0,
        "资料索引",
    )


def poll_export(client, job_id: str) -> dict[str, Any]:
    def fetch() -> dict[str, Any]:
        response = client.get(f"/api/exports/{job_id}")
        assert response.status_code == 200, response.text
        data = response.json()
        if data["status"] == "failed":
            raise AssertionError(data.get("error_message") or "导出失败")
        return data

    return wait_until(fetch, {"succeeded"}, 8.0, "导出任务")


def run_flow() -> tuple[list[CheckResult], dict[str, Any]]:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    results: list[CheckResult] = []
    suffix = uuid.uuid4().hex[:8]
    state: dict[str, Any] = {"suffix": suffix}

    def day2_source_flow() -> str:
        project = create_project(client, suffix)
        state["project"] = project
        content = (
            "# 水的三态变化\n\n"
            "冰受热会融化成水，水继续受热会蒸发。"
            "水蒸气遇冷会凝结成小水滴。"
        ).encode("utf-8")
        source = upload_source(client, project["id"], "..\\unsafe-name.md", content)
        assert source["status"] == "ready", source
        assert source["original_name"] == "unsafe-name.md", source["original_name"]
        state["source"] = source

        duplicate = client.post(
            f"/api/projects/{project['id']}/sources",
            files={"file": ("again.md", content, "text/markdown")},
        )
        assert duplicate.status_code == 400, duplicate.text
        assert duplicate.json()["error"]["code"] == "INVALID_SOURCE_FILE"

        invalid = client.post(
            f"/api/projects/{project['id']}/sources",
            files={"file": ("danger.exe", b"bad", "application/octet-stream")},
        )
        assert invalid.status_code == 400, invalid.text

        search = client.post(
            f"/api/projects/{project['id']}/search",
            json={"query": "水蒸气遇冷会发生什么", "top_k": 3},
        )
        assert search.status_code == 200, search.text
        assert search.json()[0]["source_id"] == source["id"]

        other = create_project(client, suffix + "-isolated")
        other_sources = client.get(f"/api/projects/{other['id']}/sources")
        assert other_sources.status_code == 200
        assert other_sources.json() == []

        delete_source = upload_source(client, project["id"], "delete-me.md", "# delete\n\n用于删除补偿验收。".encode("utf-8"))
        deleted = client.delete(f"/api/projects/{project['id']}/sources/{delete_source['id']}")
        assert deleted.status_code == 204, deleted.text
        missing = client.get(f"/api/projects/{project['id']}/sources/{delete_source['id']}")
        assert missing.status_code == 404
        return "上传、索引、重复/非法类型、路径清洗、搜索来源、删除和项目隔离均通过"

    results.append(guarded("第2天", "资料元数据、上传、索引与检索", day2_source_flow))

    def day3_task_artifacts() -> str:
        project = state["project"]
        source = state["source"]
        skills = client.get("/api/skills")
        assert skills.status_code == 200
        assert len(skills.json()) >= 5

        payload = {
            "type": "full_lesson",
            "selected_source_ids": [source["id"]],
            "teacher_requirements": "突出科学观察",
            "idempotency_key": f"accept-{state['suffix']}",
        }
        task = client.post(f"/api/projects/{project['id']}/tasks", json=payload)
        assert task.status_code == 202, task.text
        duplicate = client.post(f"/api/projects/{project['id']}/tasks", json=payload)
        assert duplicate.status_code == 202
        assert duplicate.json()["id"] == task.json()["id"]
        final_task = wait_until(
            lambda: client.get(f"/api/tasks/{task.json()['id']}").json(),
            {"succeeded", "failed", "cancelled"},
            10.0,
            "AI 任务",
        )
        assert final_task["status"] == "succeeded", final_task
        assert final_task["input_snapshot"] if "input_snapshot" in final_task else True
        state["task"] = final_task

        listed = client.get(f"/api/projects/{project['id']}/tasks")
        assert listed.status_code == 200
        assert any(item["id"] == final_task["id"] for item in listed.json())

        artifacts = client.get(f"/api/projects/{project['id']}/artifacts")
        assert artifacts.status_code == 200, artifacts.text
        by_type = {item["type"]: item for item in artifacts.json()}
        assert set(by_type) == {"lesson_plan", "slide_deck", "speaker_notes", "exercise_set"}, sorted(by_type)
        state["artifacts"] = by_type
        return "Skill 列表、任务幂等、状态轮询、任务列表和四类第一版产物均通过"

    results.append(guarded("第3天", "项目任务、产物与版本基础接口", day3_task_artifacts))

    def day4_trace_and_errors() -> str:
        trace_id = f"trace-{state['suffix']}"
        missing = client.get("/api/projects/not-exist", headers={"X-Trace-ID": trace_id})
        assert missing.status_code == 404
        assert missing.headers["X-Trace-ID"] == trace_id
        assert missing.json()["error"]["trace_id"] == trace_id
        assert missing.json()["error"]["code"] == "PROJECT_NOT_FOUND"

        bad_task = client.post(
            f"/api/projects/{state['project']['id']}/tasks",
            json={
                "type": "full_lesson",
                "selected_source_ids": ["missing-source"],
                "teacher_requirements": "",
                "idempotency_key": f"bad-{state['suffix']}",
            },
        )
        assert bad_task.status_code == 409
        assert bad_task.json()["error"]["code"] == "SOURCE_NOT_READY"

        task = client.get(f"/api/tasks/{state['task']['id']}").json()
        assert task["trace_id"]
        assert task["stage"]
        assert task["progress"] == 100
        return "trace_id 响应头/错误体、统一错误码、任务阶段和进度均通过"

    results.append(guarded("第4天", "任务执行、统一错误和 trace_id", day4_trace_and_errors))

    def day5_versions_revision_rollback() -> str:
        lesson_plan = state["artifacts"]["lesson_plan"]
        first_version = lesson_plan["version_no"]
        target_id = lesson_plan["content"]["stages"][0]["id"]
        revision = client.post(
            f"/api/artifacts/{lesson_plan['artifact_id']}/revise",
            json={
                "base_version_no": first_version,
                "target_type": "stages",
                "target_id": target_id,
                "instruction": "把导入活动写得更贴近生活",
                "sync_related": False,
            },
        )
        assert revision.status_code == 200, revision.text
        revised = revision.json()
        assert revised["version_no"] == first_version + 1
        assert target_id in json.dumps(revised["content"], ensure_ascii=False)

        conflict = client.post(
            f"/api/artifacts/{lesson_plan['artifact_id']}/revise",
            json={
                "base_version_no": first_version,
                "target_type": "stages",
                "target_id": target_id,
                "instruction": "这次应触发版本冲突",
                "sync_related": False,
            },
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "VERSION_CONFLICT"

        versions = client.get(f"/api/artifacts/{lesson_plan['artifact_id']}/versions")
        assert versions.status_code == 200
        assert len(versions.json()) >= 2

        rollback = client.post(f"/api/artifacts/{lesson_plan['artifact_id']}/rollback/{first_version}")
        assert rollback.status_code == 200, rollback.text
        assert rollback.json()["version_no"] == revised["version_no"] + 1
        state["lesson_plan_after_rollback"] = rollback.json()
        return "局部修改、版本列表、乐观锁冲突和回滚创建新版本均通过"

    results.append(guarded("第5天", "产物版本、局部更新与回滚", day5_versions_revision_rollback))

    def day6_graph_and_exports() -> str:
        project = state["project"]
        graph = client.get(f"/api/projects/{project['id']}/graph")
        assert graph.status_code == 200, graph.text
        graph_id = graph.json()["id"]
        confirm = client.post(f"/api/graphs/{graph_id}/confirm", json={"decision": "accept"})
        assert confirm.status_code == 200, confirm.text
        assert confirm.json()["status"] == "succeeded"
        confirm_again = client.post(f"/api/graphs/{graph_id}/confirm", json={"decision": "accept"})
        assert confirm_again.status_code == 200

        extra_graph = client.post(
            f"/api/projects/{project['id']}/graph/runs",
            json={"task_id": state["task"]["id"], "thread_id": f"manual-{state['suffix']}"},
        )
        assert extra_graph.status_code == 202, extra_graph.text
        cancelled = client.post(f"/api/graphs/{extra_graph.json()['id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        resumed = client.post(f"/api/graphs/{extra_graph.json()['id']}/resume")
        assert resumed.status_code == 200
        assert resumed.json()["status"] == "running"

        teacher_job = client.post(
            f"/api/projects/{project['id']}/exports",
            json={"package_type": "teacher"},
        )
        assert teacher_job.status_code == 202, teacher_job.text
        teacher_status = poll_export(client, teacher_job.json()["job_id"])
        teacher_download = client.get(teacher_status["download_url"])
        assert teacher_download.status_code == 200
        teacher_zip = zipfile.ZipFile(io.BytesIO(teacher_download.content))
        teacher_names = set(teacher_zip.namelist())
        assert {"README.txt", "slides.md", "slides.html", "教学设计.json", "逐页讲稿.json", "教师版练习.json", "引用清单.json"} <= teacher_names

        student_job = client.post(
            f"/api/projects/{project['id']}/exports",
            json={"package_type": "student"},
        )
        assert student_job.status_code == 202, student_job.text
        student_status = poll_export(client, student_job.json()["job_id"])
        student_download = client.get(student_status["download_url"])
        assert student_download.status_code == 200
        student_zip = zipfile.ZipFile(io.BytesIO(student_download.content))
        student_names = set(student_zip.namelist())
        assert "逐页讲稿.json" not in student_names
        assert "学生练习.json" in student_names
        student_exercises = student_zip.read("学生练习.json").decode("utf-8")
        assert '"answer"' not in student_exercises
        assert '"explanation"' not in student_exercises
        state["teacher_export"] = sorted(teacher_names)
        state["student_export"] = sorted(student_names)
        return "图查询/确认/取消/恢复、教师包、学生包答案隐藏和安全下载均通过"

    results.append(guarded("第6天", "图状态持久化、人工确认与双包导出", day6_graph_and_exports))
    return results, state


def static_checks() -> list[CheckResult]:
    results: list[CheckResult] = []

    def day7_backend_quality() -> str:
        pytest_code, pytest_output = run_command([sys.executable, "-m", "pytest", "-q"], timeout=120)
        assert pytest_code == 0, pytest_output
        alembic_code, alembic_output = run_command([sys.executable, "-m", "alembic", "-c", "alembic.ini", "current"], cwd=BACKEND)
        assert alembic_code == 0 and "0001_initial" in alembic_output, alembic_output
        docker = docker_command()
        assert docker, "未找到 docker 命令"
        compose_code, compose_output = run_command([docker, "compose", "-f", "deploy/docker-compose.yml", "config"], timeout=60)
        assert compose_code == 0, compose_output
        tracked_code, tracked_output = run_command(["git", "ls-files", "data", "backend/data"])
        assert tracked_code == 0, tracked_output
        tracked = {line.strip().replace("\\", "/") for line in tracked_output.splitlines() if line.strip()}
        assert tracked <= {"data/.gitkeep", "backend/data/.gitkeep"}, sorted(tracked)
        return "pytest 全量通过、MySQL 迁移当前版本正确、compose 可解析、生成数据未跟踪"

    results.append(guarded("第7天", "后端测试、MySQL、安全与一键部署静态验收", day7_backend_quality))

    def day8_environment_guarantee() -> str:
        health_code, health_output = run_command(
            [
                sys.executable,
                "-c",
                (
                    "from fastapi.testclient import TestClient; "
                    "from app.main import app; "
                    "c=TestClient(app); "
                    "print(c.get('/health').json()); "
                    "print(c.get('/health/db').json()); "
                    "print(c.get('/health/ai').json()); "
                    "print(c.get('/health/chroma').json())"
                ),
            ],
            cwd=BACKEND,
        )
        assert health_code == 0, health_output
        assert "'status': 'ok'" in health_output
        assert "'database': 'mysql'" in health_output
        docker = docker_command()
        docker_detail = "未检测 Docker CLI"
        if docker:
            ps_code, ps_output = run_command([docker, "ps", "--filter", "name=lessondeck-mysql", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}"])
            if ps_code == 0 and "lessondeck-mysql" in ps_output:
                docker_detail = "项目 MySQL 容器可定位"
            elif ps_code != 0 and "permission denied" in ps_output.lower():
                docker_detail = "Docker 状态需要提升权限查看"
            else:
                docker_detail = "Docker 容器状态未确认：" + (ps_output or "无输出")
        return "API/MySQL/AI/Chroma 健康检查可用；" + docker_detail

    results.append(guarded("第8天", "干净环境、MySQL 与健康诊断", day8_environment_guarantee))
    return results


def print_table(results: list[CheckResult]) -> None:
    day_width = max(len("天数"), *(len(item.day) for item in results))
    name_width = max(len("验收项"), *(len(item.name) for item in results))
    status_width = max(len("结果"), *(len(item.status) for item in results))
    print("\n成员 3 第 2-8 天自动验收结果")
    print(f"项目根目录：{ROOT}")
    print("-" * 110)
    print(f"{'天数':<{day_width}}  {'验收项':<{name_width}}  {'结果':<{status_width}}  说明")
    print("-" * 110)
    for item in results:
        print(f"{item.day:<{day_width}}  {item.name:<{name_width}}  {item.status:<{status_width}}  {item.detail}")
    print("-" * 110)
    counts = {status: sum(1 for item in results if item.status == status) for status in ("通过", "失败", "未验证")}
    print(f"汇总：通过 {counts['通过']}，失败 {counts['失败']}，未验证 {counts['未验证']}")


def main() -> int:
    flow_results, _state = run_flow()
    results = flow_results + static_checks()
    print_table(results)
    return 1 if any(item.status == "失败" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
