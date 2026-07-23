"""Live API acceptance flow. Start the stack first, preferably with AI_FORCE_FALLBACK=true."""
from __future__ import annotations

import io
import json
import os
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path


BASE = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
CASE = os.getenv("DEMO_CASE", "science")
CASES = {
    "science": {
        "subject": "科学", "grade": "小学三年级", "topic": "水的三态变化",
        "profile": "能描述日常现象", "query": "水蒸气遇冷",
        "content": None,
    },
    "language": {
        "subject": "语文", "grade": "小学四年级", "topic": "抓住关键词理解人物品质",
        "profile": "能够默读短文并圈画词句", "query": "关键词 人物品质",
        "content": "# 阅读课自编资料\n\n阅读人物故事时，可以圈画动作、语言和神态关键词，并结合上下文说明人物品质。所有判断都要回到文本证据。",
    },
    "math": {
        "subject": "数学", "grade": "小学五年级", "topic": "用方程解决实际问题",
        "profile": "会用字母表示未知数并完成整数四则运算", "query": "方程 实际问题",
        "content": "# 数学课自编资料\n\n解决实际问题时，先找等量关系，再设未知数、列方程、求解并检验。检验既要检查计算，也要回到题意。",
    },
}
if CASE not in CASES:
    raise SystemExit(f"未知 DEMO_CASE：{CASE}")
demo = CASES[CASE]


def call(path, method="GET", data=None, content_type="application/json", raw=False):
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(
        BASE + path,
        data=body,
        method=method,
        headers={"Content-Type": content_type},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
        return payload if raw else (json.loads(payload) if payload else None)


def upload(project_id: str, filename: str, payload: bytes):
    boundary = f"----LessonDeck{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: text/markdown\r\n\r\n"
    ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        f"{BASE}/api/projects/{project_id}/sources",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def wait(path: str, terminal: set[str], limit=100):
    for _ in range(limit):
        value = call(path)
        if value["status"] in terminal:
            return value
        time.sleep(0.2)
    raise AssertionError(f"timeout waiting for {path}")


health = call("/health")
assert health["status"] == "ok"
assert call("/health/db")["status"] == "ok"
ai_health = call("/health/ai")
if ai_health["configured"] and os.getenv("ALLOW_REAL_MODEL") != "1":
    raise SystemExit("拒绝意外产生模型费用：请让服务使用 AI_FORCE_FALLBACK=true，或显式设置 ALLOW_REAL_MODEL=1")

project = call("/api/projects", "POST", {
    "name": f"E2E {CASE} 课例 {int(time.time())}",
    "subject": demo["subject"],
    "grade": demo["grade"],
    "textbook_version": "自编公开样例",
    "lesson_topic": demo["topic"],
    "lesson_count": 1,
    "student_profile": demo["profile"],
    "teacher_requirements": "重视观察证据",
})
sample_path = Path(__file__).parents[2] / "samples" / "公开课例资料.md"
payload = sample_path.read_bytes() if demo["content"] is None else str(demo["content"]).encode()
source = upload(project["id"], f"{CASE}-公开课例资料.md", payload)
source = wait(f"/api/projects/{project['id']}/sources/{source['id']}", {"ready", "failed"})
assert source["status"] == "ready", source
results = call(f"/api/projects/{project['id']}/search", "POST", {"query": demo["query"], "top_k": 3})
assert results and results[0]["source_id"] == source["id"]

skill = call(f"/api/projects/{project['id']}/tasks", "POST", {
    "type": "learning_objectives",
    "selected_source_ids": [source["id"]],
    "teacher_requirements": "目标必须可观察",
    "idempotency_key": f"skill-{uuid.uuid4()}",
})
skill = wait(f"/api/tasks/{skill['id']}", {"succeeded", "failed", "cancelled"})
assert skill["status"] == "succeeded" and skill["result_snapshot"]["skill_id"] == "learning_objectives"

task = call(f"/api/projects/{project['id']}/tasks", "POST", {
    "type": "full_lesson",
    "selected_source_ids": [source["id"]],
    "teacher_requirements": "重视观察证据",
    "idempotency_key": f"smoke-{uuid.uuid4()}",
})
task = wait(f"/api/tasks/{task['id']}", {"succeeded", "failed", "cancelled"})
assert task["status"] == "succeeded", task
artifacts = call(f"/api/projects/{project['id']}/artifacts")
assert {item["type"] for item in artifacts} == {"lesson_plan", "slide_deck", "speaker_notes", "exercise_set"}
deck = next(item for item in artifacts if item["type"] == "slide_deck")
assert 12 <= len(deck["content"]["slides"]) <= 18
target = deck["content"]["slides"][0]["slide_id"]
revised = call(f"/api/artifacts/{deck['artifact_id']}/revise", "POST", {
    "base_version_no": deck["version_no"],
    "target_type": "slide",
    "target_id": target,
    "instruction": "精简页面文字",
    "sync_related": True,
})
assert revised["changed_ids"] == [target] and revised["unchanged_hashes"]
history = call(f"/api/artifacts/{deck['artifact_id']}/versions")
assert len(history) >= 2
rolled = call(f"/api/artifacts/{deck['artifact_id']}/rollback/1", "POST")
assert rolled["change_type"] == "rollback"

graph = call(f"/api/projects/{project['id']}/graph")
assert graph["status"] == "awaiting_confirmation"
assert graph["state_snapshot"]["checkpointed_at"]
call(f"/api/graphs/{graph['id']}/confirm", "POST", {"decision": "accept"})

artifacts = call(f"/api/projects/{project['id']}/artifacts")
for package_type, required in (
    ("teacher", {"lesson_plan", "slide_deck", "speaker_notes", "exercise_set"}),
    ("student", {"slide_deck", "exercise_set"}),
):
    version_ids = [item["version_id"] for item in artifacts if item["type"] in required]
    export = call(f"/api/projects/{project['id']}/exports", "POST", {
        "package_type": package_type,
        "artifact_version_ids": version_ids,
    })
    export = wait(f"/api/exports/{export['job_id']}", {"succeeded", "failed"})
    assert export["status"] == "succeeded", export
    archive = zipfile.ZipFile(io.BytesIO(call(f"/api/exports/{export['job_id']}/download", raw=True)))
    assert {"slides.md", "slides.html", "版本清单.json"}.issubset(archive.namelist())
    if package_type == "student":
        assert "逐页讲稿.json" not in archive.namelist()
        content = archive.read("学生练习.json").decode()
        assert '"answer"' not in content and '"explanation"' not in content

print(json.dumps({
    "status": "passed",
    "case": CASE,
    "project_id": project["id"],
    "trace_id": task["trace_id"],
    "graph_id": graph["id"],
}, ensure_ascii=False))
