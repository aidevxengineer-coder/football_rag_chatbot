"""Project schema migration 005 — user_knowledge_files (Ball Knowledge)."""

from alembic import op
import sqlalchemy as sa

revision = "005_user_knowledge_files"
down_revision = "004_project_file_error_message"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_knowledge_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("chunks_indexed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_indexed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="project",
    )
    op.create_index(
        "ix_project_user_knowledge_files_user_id",
        "user_knowledge_files",
        ["user_id"],
        schema="project",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_user_knowledge_files_user_id",
        table_name="user_knowledge_files",
        schema="project",
    )
    op.drop_table("user_knowledge_files", schema="project")
