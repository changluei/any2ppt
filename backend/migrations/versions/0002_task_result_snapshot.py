"""persist independent skill results

Revision ID: 0002_task_result_snapshot
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_task_result_snapshot"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ai_tasks", sa.Column("result_snapshot", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("ai_tasks", "result_snapshot")
