from __future__ import annotations

import io
import time
import zipfile

from PIL import Image


def create_project(client, theme_id="bricks"):
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
            "theme_id": theme_id,
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
    themes = client.get("/api/themes")
    assert themes.status_code == 200
    assert {item["id"] for item in themes.json()} == {"default", "seriph", "apple-basic", "bricks", "tahta"}
    recommendation = client.post(
        "/api/themes/recommend",
        json={
            "subject": "科学",
            "grade": "小学三年级",
            "lesson_topic": "观察水的变化",
            "student_profile": "",
            "teacher_requirements": "安排探究实验",
        },
    )
    assert recommendation.status_code == 200
    assert recommendation.json()["id"] == "bricks"

    project = create_project(client)
    assert project["theme_id"] == "bricks"
    assert project["theme_status"] == "ready"
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
            "theme_id": "bricks",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "单元测试项目-更新"

    missing = client.get("/api/projects/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PROJECT_NOT_FOUND"

    empty_delete = client.delete(f"/api/projects/{project['id']}")
    assert empty_delete.status_code == 204

    invalid_theme = client.post(
        "/api/projects",
        json={
            "name": "无效模板",
            "subject": "科学",
            "grade": "三年级",
            "lesson_topic": "测试",
            "theme_id": "not-installed",
        },
    )
    assert invalid_theme.status_code == 400
    assert invalid_theme.json()["error"]["code"] == "THEME_NOT_FOUND"


def test_force_delete_non_empty_project(client):
    project = create_project(client)
    upload = client.post(
        f"/api/projects/{project['id']}/sources",
        files={"file": ("sample.md", b"# sample", "text/markdown")},
    )
    assert upload.status_code == 201
    blocked = client.delete(f"/api/projects/{project['id']}")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "PROJECT_NOT_EMPTY"
    deleted = client.delete(f"/api/projects/{project['id']}", params={"force": True})
    assert deleted.status_code == 204
    assert client.get(f"/api/projects/{project['id']}").status_code == 404


def test_selected_tahta_theme_controls_slide_layouts(client):
    project = create_project(client, "tahta")
    response = client.post(
        f"/api/projects/{project['id']}/tasks",
        json={
            "type": "full_lesson",
            "selected_source_ids": [],
            "teacher_requirements": "使用步骤、对比和图解来组织页面",
            "idempotency_key": "tahta-layout-contract",
        },
    )
    assert response.status_code == 202
    task = wait_for_task(client, response.json()["id"])
    assert task["status"] == "succeeded"
    artifacts = client.get(f"/api/projects/{project['id']}/artifacts").json()
    deck = next(item for item in artifacts if item["type"] == "slide_deck")["content"]
    assert deck["theme_id"] == "tahta"
    assert deck["theme_config"]["variant"] == "notebook"
    assert {slide["layout"] for slide in deck["slides"]} <= set(deck["theme_layouts"])


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
    assert "slides.md" in archive.namelist()
    assert archive.read("slides.md").decode("utf-8").startswith("---\ntheme:")
    assert "版本清单.json" in archive.namelist()

    extra_graph = client.post(
        f"/api/projects/{project['id']}/graph/runs",
        json={"task_id": task_id, "thread_id": "checkpoint-resume-test"},
    )
    assert extra_graph.status_code == 202, extra_graph.text
    extra_graph_id = extra_graph.json()["id"]
    cancelled = client.post(f"/api/graphs/{extra_graph_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["state_snapshot"]["cancelled"] is True

    resumed = client.post(f"/api/graphs/{extra_graph_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "running"
    resumed_graph = client.get(f"/api/projects/{project['id']}/graph")
    assert resumed_graph.status_code == 200
    assert resumed_graph.json()["id"] == extra_graph_id
    assert resumed_graph.json()["status"] == "awaiting_confirmation"
    assert resumed_graph.json()["state_snapshot"]["cancelled"] is False
    resumed_nodes = {item["node_id"]: item for item in resumed_graph.json()["nodes"]}
    assert resumed_nodes["analyze_sources"]["attempt"] >= 2


def test_independent_skill_result_and_unknown_type(client):
    project = create_project(client)
    response = client.post(
        f"/api/projects/{project['id']}/tasks",
        json={
            "type": "learning_objectives",
            "selected_source_ids": [],
            "teacher_requirements": "突出可观察行为",
            "idempotency_key": "independent-skill",
        },
    )
    assert response.status_code == 202, response.text
    task = wait_for_task(client, response.json()["id"])
    assert task["status"] == "succeeded"
    assert task["result_artifact_id"] is None
    assert task["result_snapshot"]["skill_id"] == "learning_objectives"
    assert task["result_snapshot"]["result"]["objectives"]
    assert client.get(f"/api/projects/{project['id']}/artifacts").json() == []

    unknown = client.post(
        f"/api/projects/{project['id']}/tasks",
        json={
            "type": "not-a-real-skill",
            "selected_source_ids": [],
            "teacher_requirements": "",
            "idempotency_key": "unknown-skill",
        },
    )
    assert unknown.status_code == 400
    assert unknown.json()["error"]["code"] == "UNKNOWN_TASK_TYPE"


def test_version_metadata_rollback_and_student_privacy(client):
    project = create_project(client)
    response = client.post(
        f"/api/projects/{project['id']}/tasks",
        json={
            "type": "full_lesson",
            "selected_source_ids": [],
            "teacher_requirements": "",
            "idempotency_key": "version-flow",
        },
    )
    task = wait_for_task(client, response.json()["id"])
    assert task["status"] == "succeeded"
    artifacts = client.get(f"/api/projects/{project['id']}/artifacts").json()
    slide_deck = next(item for item in artifacts if item["type"] == "slide_deck")
    assert slide_deck["content"]["theme_id"] == "bricks"
    assert slide_deck["content"]["theme"] == "@slidev/theme-bricks"
    target = slide_deck["content"]["slides"][0]["slide_id"]
    changed = client.post(
        f"/api/artifacts/{slide_deck['artifact_id']}/revise",
        json={
            "base_version_no": 1,
            "target_type": "slide",
            "target_id": target,
            "instruction": "精简页面文字",
            "sync_related": True,
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["changed_ids"] == [target]
    assert changed.json()["unchanged_hashes"]
    rollback = client.post(f"/api/artifacts/{slide_deck['artifact_id']}/rollback/1")
    assert rollback.status_code == 200
    assert rollback.json()["change_type"] == "rollback"
    assert rollback.json()["version_no"] == 3
    direct_markdown = client.post(
        f"/api/artifacts/{slide_deck['artifact_id']}/markdown",
        json={
            "base_version_no": 3,
            "slide_id": target,
            "markdown": "# 现场修改后的标题\n\n- 教师直接编辑\n- 右侧实时预览",
        },
    )
    assert direct_markdown.status_code == 200, direct_markdown.text
    edited = direct_markdown.json()
    assert edited["version_no"] == 4
    assert edited["change_type"] == "manual_markdown"
    assert edited["changed_ids"] == [target]
    assert edited["unchanged_hashes"]
    edited_slide = next(item for item in edited["content"]["slides"] if item["slide_id"] == target)
    assert edited_slide["title"] == "现场修改后的标题"
    assert "教师直接编辑" in edited_slide["markdown"]

    conflict = client.post(
        f"/api/artifacts/{slide_deck['artifact_id']}/markdown",
        json={
            "base_version_no": 3,
            "slide_id": target,
            "markdown": "# 过期修改",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["current_version"] == 4

    image_buffer = io.BytesIO()
    Image.new("RGB", (320, 180), color=(66, 135, 245)).save(image_buffer, format="PNG")
    uploaded_image = client.post(
        f"/api/projects/{project['id']}/images",
        files={"file": ("课堂观察.png", image_buffer.getvalue(), "image/png")},
    )
    assert uploaded_image.status_code == 201, uploaded_image.text
    image_data = uploaded_image.json()
    assert image_data["width"] == 320
    assert image_data["height"] == 180
    assert client.get(image_data["content_url"]).status_code == 200
    assert len(client.get(f"/api/projects/{project['id']}/images").json()) == 1

    placement = client.post(
        f"/api/artifacts/{slide_deck['artifact_id']}/images",
        json={
            "base_version_no": 4,
            "slide_id": target,
            "image_id": image_data["id"],
            "position": "right",
            "caption": "课堂观察图片",
        },
    )
    assert placement.status_code == 200, placement.text
    placed = placement.json()
    assert placed["version_no"] == 5
    placed_slide = next(item for item in placed["content"]["slides"] if item["slide_id"] == target)
    assert placed_slide["images"][0]["image_id"] == image_data["id"]
    placement_id = placed_slide["images"][0]["placement_id"]

    graph = client.get(f"/api/projects/{project['id']}/graph").json()
    client.post(f"/api/graphs/{graph['id']}/confirm", json={"decision": "accept"})
    refreshed = client.get(f"/api/projects/{project['id']}/artifacts").json()
    version_ids = [
        item["version_id"]
        for item in refreshed
        if item["type"] in {"slide_deck", "exercise_set"}
    ]
    export = client.post(
        f"/api/projects/{project['id']}/exports",
        json={"package_type": "student", "artifact_version_ids": version_ids},
    )
    assert export.status_code == 202, export.text
    job_id = export.json()["job_id"]
    for _ in range(80):
        status = client.get(f"/api/exports/{job_id}").json()
        if status["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.05)
    archive = zipfile.ZipFile(io.BytesIO(client.get(f"/api/exports/{job_id}/download").content))
    assert "逐页讲稿.json" not in archive.namelist()
    student = archive.read("学生练习.json").decode("utf-8")
    assert '"answer"' not in student
    assert '"explanation"' not in student

    current_deck = next(item for item in refreshed if item["type"] == "slide_deck")
    pptx = client.post(
        f"/api/projects/{project['id']}/exports",
        json={"package_type": "pptx", "artifact_version_ids": [current_deck["version_id"]]},
    )
    assert pptx.status_code == 202, pptx.text
    pptx_job_id = pptx.json()["job_id"]
    for _ in range(80):
        pptx_status = client.get(f"/api/exports/{pptx_job_id}").json()
        if pptx_status["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.05)
    assert pptx_status["status"] == "succeeded", pptx_status
    pptx_download = client.get(f"/api/exports/{pptx_job_id}/download")
    assert pptx_download.status_code == 200
    assert "presentationml.presentation" in pptx_download.headers["content-type"]
    pptx_archive = zipfile.ZipFile(io.BytesIO(pptx_download.content))
    assert "ppt/slides/slide1.xml" in pptx_archive.namelist()
    assert any(name.startswith("ppt/media/image") for name in pptx_archive.namelist())

    removed = client.delete(
        f"/api/artifacts/{slide_deck['artifact_id']}/images/{placement_id}",
        params={"base_version_no": 5},
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["version_no"] == 6
    removed_slide = next(item for item in removed.json()["content"]["slides"] if item["slide_id"] == target)
    assert removed_slide["images"] == []
