"""add durable official and personal knowledge bases

Revision ID: 0005_knowledge_bases
Revises: 0004_project_theme
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_knowledge_bases"
down_revision = "0004_project_theme"
branch_labels = None
depends_on = None


LIBRARIES = (
    ("official-chinese", "官方语文知识库", "official", "语文", "课标、教材知识、阅读与写作教学资料", True),
    ("official-mathematics", "官方数学知识库", "official", "数学", "小学数学概念、题型、方法与课程资料", True),
    ("official-english", "官方英语知识库", "official", "英语", "小学英语词汇、语法、阅读与课堂活动资料", True),
    ("personal", "个人知识库", "personal", "", "使用过程中上传并持续积累的个人资料", False),
)


def upgrade():
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("subject", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="empty"),
        sa.Column("read_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("document_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_knowledge_base_kind", "knowledge_bases", ["kind"])
    op.create_index("ix_knowledge_base_status", "knowledge_bases", ["status"])
    table = sa.table(
        "knowledge_bases",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("kind", sa.String),
        sa.column("subject", sa.String),
        sa.column("description", sa.Text),
        sa.column("status", sa.String),
        sa.column("read_only", sa.Boolean),
    )
    op.bulk_insert(
        table,
        [
            {
                "id": library_id,
                "name": name,
                "kind": kind,
                "subject": subject,
                "description": description,
                "status": "empty",
                "read_only": read_only,
            }
            for library_id, name, kind, subject, description, read_only in LIBRARIES
        ],
    )

    op.add_column("projects", sa.Column("knowledge_base_ids", sa.JSON(), nullable=True))
    op.execute("UPDATE projects SET knowledge_base_ids = '[]' WHERE knowledge_base_ids IS NULL")
    op.alter_column("projects", "knowledge_base_ids", existing_type=sa.JSON(), nullable=False)

    op.add_column("source_documents", sa.Column("knowledge_base_id", sa.String(length=36), nullable=True))
    op.execute("UPDATE source_documents SET knowledge_base_id = 'personal'")
    op.alter_column("source_documents", "knowledge_base_id", existing_type=sa.String(length=36), nullable=False)
    op.alter_column("source_documents", "project_id", existing_type=sa.String(length=36), nullable=True)
    op.create_foreign_key(
        "fk_source_knowledge_base",
        "source_documents",
        "knowledge_bases",
        ["knowledge_base_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("uq_project_source_hash", "source_documents", type_="unique")
    op.create_unique_constraint(
        "uq_knowledge_base_source_hash",
        "source_documents",
        ["knowledge_base_id", "sha256"],
    )
    op.create_index("ix_source_documents_knowledge_base_id", "source_documents", ["knowledge_base_id"])
    op.create_index("ix_source_library_status", "source_documents", ["knowledge_base_id", "status"])
    op.create_index("ix_source_library_created", "source_documents", ["knowledge_base_id", "created_at"])


def downgrade():
    op.drop_index("ix_source_library_created", table_name="source_documents")
    op.drop_index("ix_source_library_status", table_name="source_documents")
    op.drop_index("ix_source_documents_knowledge_base_id", table_name="source_documents")
    op.drop_constraint("uq_knowledge_base_source_hash", "source_documents", type_="unique")
    op.create_unique_constraint("uq_project_source_hash", "source_documents", ["project_id", "sha256"])
    op.drop_constraint("fk_source_knowledge_base", "source_documents", type_="foreignkey")
    op.drop_column("source_documents", "knowledge_base_id")
    op.drop_column("projects", "knowledge_base_ids")
    op.drop_index("ix_knowledge_base_status", table_name="knowledge_bases")
    op.drop_index("ix_knowledge_base_kind", table_name="knowledge_bases")
    op.drop_table("knowledge_bases")
