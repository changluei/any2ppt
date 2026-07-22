"""initial tables"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("subject", sa.String(length=40), nullable=False),
        sa.Column("grade", sa.String(length=40), nullable=False),
        sa.Column("textbook_version", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("lesson_topic", sa.String(length=160), nullable=False),
        sa.Column("lesson_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("student_profile", sa.Text(), nullable=False),
        sa.Column("teacher_requirements", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_projects_status", "projects", ["status"])
    op.create_index("ix_projects_status_updated", "projects", ["status", "updated_at"])

    op.create_table(
        "source_documents",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=80), nullable=False),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="uploaded"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("project_id", "sha256", name="uq_project_source_hash"),
    )
    op.create_index("ix_source_documents_project_id", "source_documents", ["project_id"])
    op.create_index("ix_source_documents_status", "source_documents", ["status"])
    op.create_index("ix_source_project_status", "source_documents", ["project_id", "status"])
    op.create_index("ix_source_project_created", "source_documents", ["project_id", "created_at"])

    op.create_table(
        "ai_tasks",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("stage", sa.String(length=64), nullable=False, server_default="waiting"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trace_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("result_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("project_id", "idempotency_key", name="uq_task_idempotency"),
    )
    op.create_index("ix_ai_tasks_project_id", "ai_tasks", ["project_id"])
    op.create_index("ix_ai_tasks_status", "ai_tasks", ["status"])
    op.create_index("ix_ai_tasks_trace_id", "ai_tasks", ["trace_id"])
    op.create_index("ix_task_project_created", "ai_tasks", ["project_id", "created_at"])
    op.create_index("ix_task_status_created", "ai_tasks", ["status", "created_at"])

    op.create_table(
        "lesson_artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("current_version_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("project_id", "type", name="uq_project_artifact_type"),
    )
    op.create_index("ix_lesson_artifacts_project_id", "lesson_artifacts", ["project_id"])
    op.create_index("ix_lesson_artifacts_type", "lesson_artifacts", ["type"])
    op.create_index("ix_artifact_project_type", "lesson_artifacts", ["project_id", "type"])

    op.create_table(
        "artifact_versions",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("artifact_id", sa.String(length=36), sa.ForeignKey("lesson_artifacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.String(length=36), sa.ForeignKey("artifact_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("change_type", sa.String(length=32), nullable=False, server_default="generated"),
        sa.Column("changed_ids", sa.JSON(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("artifact_id", "version_no", name="uq_artifact_version"),
    )
    op.create_index("ix_artifact_versions_artifact_id", "artifact_versions", ["artifact_id"])
    op.create_index("ix_artifact_version_artifact_no", "artifact_versions", ["artifact_id", "version_no"])

    op.create_table(
        "graph_runs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("ai_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("thread_id", sa.String(length=80), nullable=False),
        sa.Column("checkpoint_ref", sa.String(length=200), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("current_node", sa.String(length=64), nullable=False, server_default="analyze_sources"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.JSON(), nullable=False),
        sa.Column("nodes", sa.JSON(), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("state_snapshot", sa.JSON(), nullable=False),
        sa.Column("human_decision", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_graph_runs_project_id", "graph_runs", ["project_id"])
    op.create_index("ix_graph_runs_task_id", "graph_runs", ["task_id"])
    op.create_index("ix_graph_runs_thread_id", "graph_runs", ["thread_id"])
    op.create_index("ix_graph_runs_status", "graph_runs", ["status"])
    op.create_index("ix_graph_project_status", "graph_runs", ["project_id", "status"])
    op.create_index("ix_graph_task", "graph_runs", ["task_id"])
    op.create_index("ix_graph_thread", "graph_runs", ["thread_id"])

    op.create_table(
        "export_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("package_type", sa.String(length=20), nullable=False),
        sa.Column("selected_versions", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_export_jobs_project_id", "export_jobs", ["project_id"])
    op.create_index("ix_export_jobs_status", "export_jobs", ["status"])
    op.create_index("ix_export_project_status", "export_jobs", ["project_id", "status"])


def downgrade():
    op.drop_index("ix_export_project_status", table_name="export_jobs")
    op.drop_index("ix_export_jobs_status", table_name="export_jobs")
    op.drop_index("ix_export_jobs_project_id", table_name="export_jobs")
    op.drop_table("export_jobs")

    op.drop_index("ix_graph_thread", table_name="graph_runs")
    op.drop_index("ix_graph_task", table_name="graph_runs")
    op.drop_index("ix_graph_project_status", table_name="graph_runs")
    op.drop_index("ix_graph_runs_status", table_name="graph_runs")
    op.drop_index("ix_graph_runs_thread_id", table_name="graph_runs")
    op.drop_index("ix_graph_runs_task_id", table_name="graph_runs")
    op.drop_index("ix_graph_runs_project_id", table_name="graph_runs")
    op.drop_table("graph_runs")

    op.drop_index("ix_artifact_version_artifact_no", table_name="artifact_versions")
    op.drop_index("ix_artifact_versions_artifact_id", table_name="artifact_versions")
    op.drop_table("artifact_versions")

    op.drop_index("ix_artifact_project_type", table_name="lesson_artifacts")
    op.drop_index("ix_lesson_artifacts_type", table_name="lesson_artifacts")
    op.drop_index("ix_lesson_artifacts_project_id", table_name="lesson_artifacts")
    op.drop_table("lesson_artifacts")

    op.drop_index("ix_task_status_created", table_name="ai_tasks")
    op.drop_index("ix_task_project_created", table_name="ai_tasks")
    op.drop_index("ix_ai_tasks_trace_id", table_name="ai_tasks")
    op.drop_index("ix_ai_tasks_status", table_name="ai_tasks")
    op.drop_index("ix_ai_tasks_project_id", table_name="ai_tasks")
    op.drop_table("ai_tasks")

    op.drop_index("ix_source_project_created", table_name="source_documents")
    op.drop_index("ix_source_project_status", table_name="source_documents")
    op.drop_index("ix_source_documents_status", table_name="source_documents")
    op.drop_index("ix_source_documents_project_id", table_name="source_documents")
    op.drop_table("source_documents")

    op.drop_index("ix_projects_status_updated", table_name="projects")
    op.drop_index("ix_projects_status", table_name="projects")
    op.drop_table("projects")
