"""Initial V2 schema

Revision ID: 001
Revises: None
Create Date: 2026-07-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ── Workspaces ────────────────────────────────────────────────────────
    op.create_table(
        "workspaces",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── Users ─────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "workspace_id", sa.UUID(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── Jobs ──────────────────────────────────────────────────────────────
    op.create_table(
        "jobs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "workspace_id", sa.UUID(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),  # JobConfig: skills, weights, knockouts
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── Documents ─────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "job_id", sa.UUID(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True,  # NULL for /ats-check
        ),
        sa.Column("s3_key", sa.String(500)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("structural_parse_s3_key", sa.String(500), nullable=True),
        sa.Column("extraction", sa.JSON(), nullable=True),
        sa.Column("nova_fields_used", sa.Integer(), server_default=sa.text("0")),
        # pgvector: 384-dim for all-MiniLM-L6-v2, NULL unless ambiguous-band tiebreak
        sa.Column("embedding", sa.Text(), nullable=True),  # stored as vector(384) via raw SQL
        sa.Column("status", sa.String(20), server_default=sa.text("'uploaded'")),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("job_id", "content_hash", name="uq_documents_job_content"),
    )
    # Add the actual vector column via raw SQL (SQLAlchemy doesn't know vector type)
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE documents ADD COLUMN embedding vector(384)")

    # ── Fallback Records ──────────────────────────────────────────────────
    op.create_table(
        "fallback_records",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "document_id", sa.UUID(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("field_name", sa.String(50), nullable=False),
        sa.Column("raw_text_chunk", sa.Text(), nullable=False),
        sa.Column("deterministic_confidence", sa.Float(), nullable=False),
        sa.Column("nova_model_used", sa.String(30), nullable=False),
        sa.Column("nova_response", sa.JSON(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── ATS Results ───────────────────────────────────────────────────────
    op.create_table(
        "ats_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "document_id", sa.UUID(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=True,  # NULL for /ats-check
        ),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column("ats_score", sa.Float(), nullable=False),
        sa.Column("flags", sa.JSON(), nullable=False),
        sa.Column("fix_suggestions", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── Scorings ──────────────────────────────────────────────────────────
    op.create_table(
        "scorings",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "document_id", sa.UUID(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "job_id", sa.UUID(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("knockout_result", sa.JSON(), nullable=False),
        sa.Column("skill_score", sa.Float(), nullable=False),
        sa.Column("experience_score", sa.Float(), nullable=False),
        sa.Column("education_score", sa.Float(), nullable=False),
        sa.Column("semantic_score", sa.Float(), nullable=True),  # nullable — conditional
        sa.Column("skill_matches", sa.JSON(), nullable=False),
        sa.Column("flags", sa.JSON(), nullable=False),
        sa.Column("candidate_status", sa.String(20), server_default=sa.text("'active'")),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("document_id", "job_id", name="uq_scorings_doc_job"),
    )

    # ── Skill Graph ───────────────────────────────────────────────────────
    op.create_table(
        "skill_nodes",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("aliases", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("domain", sa.String(50), nullable=True),
        sa.Column("level", sa.String(20), nullable=True),
    )

    op.create_table(
        "skill_edges",
        sa.Column(
            "from_skill", sa.UUID(),
            sa.ForeignKey("skill_nodes.id"), nullable=False,
        ),
        sa.Column(
            "to_skill", sa.UUID(),
            sa.ForeignKey("skill_nodes.id"), nullable=False,
        ),
        sa.Column("edge_type", sa.String(30), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("from_skill", "to_skill", "edge_type"),
    )

    # ── Indexes (from design.md §7) ───────────────────────────────────────
    op.create_index("idx_documents_job_id", "documents", ["job_id"])
    op.create_index("idx_documents_content_hash", "documents", ["content_hash"])
    op.create_index("idx_fallback_records_document", "fallback_records", ["document_id"])
    op.create_index("idx_ats_results_document", "ats_results", ["document_id"])
    op.create_index("idx_scorings_job_id", "scorings", ["job_id"])
    # HNSW index for vector similarity (conditional tiebreaker)
    op.execute(
        "CREATE INDEX idx_documents_embedding ON documents "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_documents_embedding")
    op.drop_index("idx_scorings_job_id")
    op.drop_index("idx_ats_results_document")
    op.drop_index("idx_fallback_records_document")
    op.drop_index("idx_documents_content_hash")
    op.drop_index("idx_documents_job_id")
    op.drop_table("skill_edges")
    op.drop_table("skill_nodes")
    op.drop_table("scorings")
    op.drop_table("ats_results")
    op.drop_table("fallback_records")
    op.drop_table("documents")
    op.drop_table("jobs")
    op.drop_table("users")
    op.drop_table("workspaces")
    op.execute("DROP EXTENSION IF EXISTS vector")
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
