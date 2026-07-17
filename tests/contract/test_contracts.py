import json
from pathlib import Path
import jsonschema


def test_task_contract_accepts_only_frozen_statuses():
    schema = json.loads(Path("contracts/schemas.json").read_text("utf-8"))
    task = {"task_id": "t1", "type": "full_lesson", "status": "running", "stage": "生成", "progress": 50, "trace_id": "trace"}
    jsonschema.validate(task, schema["$defs"]["Task"])
    task["status"] = "done"
    try:
        jsonschema.validate(task, schema["$defs"]["Task"])
    except jsonschema.ValidationError:
        return
    raise AssertionError("非法状态必须被契约拒绝")

