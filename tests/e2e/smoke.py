"""运行前先启动完整服务：python tests/e2e/smoke.py"""
import json
import time
import urllib.request

BASE = "http://localhost:8000"

def call(path, method="GET", data=None, content_type="application/json"):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(BASE + path, data=body, method=method, headers={"Content-Type": content_type})
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read()) if response.length != 0 else None

health = call("/health")
assert health["status"] == "ok"
project = call("/api/projects", "POST", {"name":"E2E 课例","subject":"科学","grade":"小学三年级","textbook_version":"自编公开样例","lesson_topic":"水的三态变化","lesson_count":1,"student_profile":"能描述日常现象","teacher_requirements":"重视观察证据"})
task = call(f"/api/projects/{project['id']}/tasks", "POST", {"type":"full_lesson","selected_source_ids":[],"teacher_requirements":"","idempotency_key":f"smoke-{time.time()}"})
for _ in range(30):
    task = call(f"/api/tasks/{task['id']}")
    if task["status"] in {"succeeded", "failed"}: break
    time.sleep(.5)
assert task["status"] == "succeeded", task
artifacts = call(f"/api/projects/{project['id']}/artifacts")
assert {a["type"] for a in artifacts} == {"lesson_plan","slide_deck","speaker_notes","exercise_set"}
print("E2E smoke passed", project["id"], task["trace_id"])

