from __future__ import annotations

from datetime import datetime

from app.core.database import SessionLocal
from app.models import AITask, ExportJob, GraphRun


def recover_interrupted_work() -> dict[str, int]:
    """Close stale in-process jobs after a restart so the UI can offer an explicit retry."""
    db = SessionLocal()
    counts = {"tasks": 0, "graphs": 0, "exports": 0}
    try:
        tasks = db.query(AITask).filter(AITask.status.in_(["pending", "running"])).all()
        for task in tasks:
            task.status = "failed"
            task.stage = "服务重启，等待重试"
            task.error_code = "WORKER_RESTARTED"
            task.error_message = "后台进程在任务完成前重启，请点击重试。"
            task.finished_at = datetime.utcnow()
        counts["tasks"] = len(tasks)

        graphs = db.query(GraphRun).filter(GraphRun.status == "running").all()
        for graph in graphs:
            graph.status = "failed"
            graph.state_snapshot = {
                **(graph.state_snapshot or {}),
                "recovery_message": "服务重启后已中止本次执行，可从最近检查点恢复。",
            }
        counts["graphs"] = len(graphs)

        exports = db.query(ExportJob).filter(ExportJob.status.in_(["pending", "running"])).all()
        for job in exports:
            job.status = "failed"
            job.error_message = "服务重启导致导出中断，请重新导出。"
        counts["exports"] = len(exports)
        db.commit()
        return counts
    finally:
        db.close()
