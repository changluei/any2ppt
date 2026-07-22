from __future__ import annotations

import io
import time
import zipfile


def create_project(client):
    response = client.post(
        "/api/projects",
        json={
            "name": "单元测试项目",
            "subject": "科学",
            "grade": "三年级",
            "textbook_version": "自编",
            "lesson_topic": "水的三态变化",
            "lesson_count": 1,
            "student_profile": "能观察并描述简单现象",
            "teacher_requirements": "强调实验安全",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def wait_for_task(client, task_id: str, timeout: float = 8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/tasks/{task_id}")
        assert response.status_code == 200, response.text
        task = response.json()
        if task["status"] in {"succeeded", "failed", "cancelled"}:
            return task
        time.sleep(0.1)
    raise AssertionError("task did not finish in time")


def wait_for_source(client, project_id: str, source_id: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/projects/{project_id}/sources/{source_id}")
        assert response.status_code == 200, response.text
        source = response.json()
        if source["status"] in {"ready", "failed"}:
            return source
        time.sleep(0.1)
    raise AssertionError("source did not finish indexing")


def test_health_and_project_crud(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/health/db").json()["status"] == "ok"
    assert client.get("/health/ai").json()["status"] in {"ok", "degraded"}
    assert client.get("/health/chroma").status_code == 200

    project = create_project(client)
    fetched = client.get(f"/api/projects/{project['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["lesson_topic"] == "水的三态变化"

    updated = client.put(
        f"/api/projects/{project['id']}",
        json={
            "name": "单元测试项目-更新",
            "subject": "科学",
            "grade": "三年级",
            "textbook_version": "自编",
            "lesson_topic": "水的三态变化",
            "lesson_count": 1,
            "student_profile": "能观察并描述简单现象",
            "teacher_requirements": "强调实验安全",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "单元测试项目-更新"

    missing = client.get("/api/projects/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PROJECT_NOT_FOUND"

    empty_delete = client.delete(f"/api/projects/{project['id']}")
    assert empty_delete.status_code == 204


def test_source_task_graph_and_export_flow(client):
    project = create_project(client)
    sample = (
        "# 水的三态变化\n\n"
        "冰受热会融化成水，水继续受热会蒸发。"
        "水蒸气遇冷会凝结成小水滴。"
    ).encode("utf-8")

    upload = client.post(
        f"/api/projects/{project['id']}/sources",
        files={"file": ("sample.md", sample, "text/markdown")},
    )
    assert upload.status_code == 201, upload.text
    source = wait_for_source(client, project["id"], upload.json()["id"])
    assert source["status"] == "ready"

    listed = client.get(f"/api/projects/{project['id']}/sources")
    assert listed.status_code == 200
    assert listed.json()[0]["original_name"] == "sample.md"

    search = client.post(
        f"/api/projects/{project['id']}/search",
        json={"query": "水遇冷会发生什么", "top_k": 3},
    )
    assert search.status_code == 200, search.text
    assert search.json()
    assert search.json()[0]["source_id"] == source["id"]

    task_payload = {
        "type": "full_lesson",
        "selected_source_ids": [source["id"]],
        "teacher_requirements": "突出科学观察",
        "idempotency_key": "test-idempotency-key",
    }
    task = client.post(f"/api/projects/{project['id']}/tasks", json=task_payload)
    assert task.status_code == 202, task.text
    task_id = task.json()["id"]
    duplicate = client.post(f"/api/projects/{project['id']}/tasks", json=task_payload)
    assert duplicate.status_code == 202
    assert duplicate.json()["id"] == task_id

    final_task = wait_for_task(client, task_id)
    assert final_task["status"] == "succeeded"

    artifacts = client.get(f"/api/projects/{project['id']}/artifacts")
    assert artifacts.status_code == 200
    artifact_types = {item["type"] for item in artifacts.json()}
    assert artifact_types == {"lesson_plan", "slide_deck", "speaker_notes", "exercise_set"}

    lesson_plan = next(item for item in artifacts.json() if item["type"] == "lesson_plan")
    version_one = client.get(f"/api/artifacts/{lesson_plan['artifact_id']}")
    assert version_one.status_code == 200
    revision = client.post(
        f"/api/artifacts/{lesson_plan['artifact_id']}/revise",
        json={
            "base_version_no": lesson_plan["version_no"],
            "target_type": "stages",
            "target_id": lesson_plan["content"]["stages"][0]["id"],
            "instruction": "把导入活动写得更贴近生活",
            "sync_related": False,
        },
    )
    assert revision.status_code == 200, revision.text
    assert revision.json()["version_no"] == lesson_plan["version_no"] + 1

    graph = client.get(f"/api/projects/{project['id']}/graph")
    assert graph.status_code == 200
    assert graph.json()["status"] in {"awaiting_confirmation", "running", "succeeded"}

    graph_id = graph.json()["id"]
    confirmed = client.post(f"/api/graphs/{graph_id}/confirm", json={"decision": "accept"})
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "succeeded"

    export_job = client.post(
        f"/api/projects/{project['id']}/exports",
        json={"package_type": "teacher"},
    )
    assert export_job.status_code == 202, export_job.text
    job_id = export_job.json()["job_id"]

    deadline = time.time() + 8.0
    while time.time() < deadline:
        status = client.get(f"/api/exports/{job_id}")
        assert status.status_code == 200, status.text
        data = status.json()
        if data["status"] == "succeeded":
            break
        if data["status"] == "failed":
            raise AssertionError(data["error_message"])
        time.sleep(0.1)
    else:
        raise AssertionError("export did not finish in time")

    download = client.get(f"/api/exports/{job_id}/download")
    assert download.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(download.content))
    assert "README.txt" in archive.namelist()
    assert any(name.endswith(".json") for name in archive.namelist())
