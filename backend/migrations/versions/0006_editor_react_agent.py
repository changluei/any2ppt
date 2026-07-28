"""add persistent editor ReAct agent messages

Revision ID: 0006_editor_react_agent
Revises: 0005_knowledge_bases
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_editor_react_agent"
down_revision = "0005_knowledge_bases"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "editor_agent_messages",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "image_id",
            sa.String(length=36),
            sa.ForeignKey("project_images.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("image_name", sa.String(length=255), nullable=True),
        sa.Column("trace_id", sa.String(length=36), nullable=True),
        sa.Column("tool_trace", sa.JSON(), nullable=False),
        sa.Column("artifact_version_no", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_editor_agent_messages_project_id",
        "editor_agent_messages",
        ["project_id"],
    )
    op.create_index(
        "ix_editor_agent_project_created",
        "editor_agent_messages",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_editor_agent_trace",
        "editor_agent_messages",
        ["trace_id"],
    )


def downgrade():
    op.drop_index("ix_editor_agent_trace", table_name="editor_agent_messages")
    op.drop_index("ix_editor_agent_project_created", table_name="editor_agent_messages")
    op.drop_index("ix_editor_agent_messages_project_id", table_name="editor_agent_messages")
    op.drop_table("editor_agent_messages")
