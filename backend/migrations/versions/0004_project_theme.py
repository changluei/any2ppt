"""store the selected project theme

Revision ID: 0004_project_theme
Revises: 0003_project_images
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_project_theme"
down_revision = "0003_project_images"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "projects",
        sa.Column("theme_id", sa.String(length=64), nullable=False, server_default="default"),
    )
    op.add_column(
        "projects",
        sa.Column("theme_status", sa.String(length=24), nullable=False, server_default="selected"),
    )


def downgrade():
    op.drop_column("projects", "theme_status")
    op.drop_column("projects", "theme_id")
