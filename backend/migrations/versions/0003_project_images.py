"""add project image assets

Revision ID: 0003_project_images
Revises: 0002_task_result_snapshot
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_project_images"
down_revision = "0002_task_result_snapshot"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_images",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=80), nullable=False),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("project_id", "sha256", name="uq_project_image_hash"),
    )
    op.create_index("ix_project_images_project_id", "project_images", ["project_id"])
    op.create_index("ix_project_image_created", "project_images", ["project_id", "created_at"])


def downgrade():
    op.drop_index("ix_project_image_created", table_name="project_images")
    op.drop_index("ix_project_images_project_id", table_name="project_images")
    op.drop_table("project_images")
