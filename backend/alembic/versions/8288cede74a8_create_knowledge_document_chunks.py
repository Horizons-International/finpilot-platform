# mypy: ignore-errors
# fmt: off

"""create knowledge document chunks

Revision ID: 8288cede74a8
Revises: 145bb8fa765d
Create Date: 2026-09-18 14:58:23.420352

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8288cede74a8"
down_revision: Union[str, Sequence[str], None] = "145bb8fa765d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS
        ix_knowledge_document_chunks_embedding_hnsw
        ON knowledge_document_chunks
        USING hnsw (embedding vector_cosine_ops)
        """)

    op.drop_index(
        op.f("ix_knowledge_document_chunks_embedding_hnsw"),
        table_name="knowledge_document_chunks",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_using="hnsw",
    )
    op.create_unique_constraint(
        "uq_knowledge_document_chunks_document_index",
        "knowledge_document_chunks",
        ["knowledge_document_id", "chunk_index"],
    )


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS
        ix_knowledge_document_chunks_embedding_hnsw
        """)

    op.drop_constraint(
        "uq_knowledge_document_chunks_document_index",
        "knowledge_document_chunks",
        type_="unique",
    )
    op.create_index(
        op.f("ix_knowledge_document_chunks_embedding_hnsw"),
        "knowledge_document_chunks",
        ["embedding"],
        unique=False,
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_using="hnsw",
    )
