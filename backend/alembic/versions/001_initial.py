"""
Initial database migration — creates all 4 core tables.

Tables created:
  - campaigns     : Campaign submissions with creator info and workflow status
  - ai_analyses   : AI analysis results per campaign (risk scores, dimensions, flags)
  - reviews       : Human reviewer decisions with override tracking
  - audit_logs    : Append-only compliance audit trail

Revision ID: 001_initial
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # campaigns
    # ------------------------------------------------------------------
    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("story", sa.Text(), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("goal_amount", sa.DECIMAL(12, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True, server_default="USD"),
        # Creator fields (denormalised for fast queue queries)
        sa.Column("creator_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("creator_name", sa.String(255), nullable=True),
        sa.Column("creator_email", sa.String(255), nullable=True),
        sa.Column("creator_country", sa.String(2), nullable=True),
        sa.Column("creator_account_age_days", sa.Integer(), nullable=True),
        # Beneficiary / org context
        sa.Column("beneficiary_country", sa.String(2), nullable=True),
        sa.Column("organization_name", sa.Text(), nullable=True),
        # Workflow status
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        # Denormalised AI recommendation for fast filtering
        sa.Column("ai_recommendation", sa.String(10), nullable=True),
        sa.Column("ai_risk_level", sa.String(10), nullable=True),
        sa.Column("ai_risk_score", sa.Integer(), nullable=True),
        # Raw submission payload
        sa.Column("raw_data", postgresql.JSONB(), nullable=True),
        # Timestamps
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("idx_campaigns_status", "campaigns", ["status"])
    op.create_index("idx_campaigns_risk_level", "campaigns", ["ai_risk_level"])
    op.create_index("idx_campaigns_submitted_at", "campaigns", ["submitted_at"])

    # ------------------------------------------------------------------
    # ai_analyses
    # ------------------------------------------------------------------
    op.create_table(
        "ai_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(10), nullable=False),
        sa.Column("recommendation", sa.String(10), nullable=False),
        sa.Column("confidence", sa.DECIMAL(3, 2), nullable=True),
        sa.Column("reasoning_summary", sa.Text(), nullable=True),
        sa.Column("risk_dimensions", postgresql.JSONB(), nullable=True),
        sa.Column("flags", postgresql.JSONB(), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        # Enforce valid risk_score range at DB level
        sa.CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_analyses_risk_score_range"),
    )
    op.create_index("idx_analyses_campaign", "ai_analyses", ["campaign_id"])
    op.create_index("idx_analyses_created_at", "ai_analyses", ["created_at"])

    # ------------------------------------------------------------------
    # reviews
    # ------------------------------------------------------------------
    op.create_table(
        "reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reviewer_id", sa.String(100), nullable=False),
        sa.Column("decision", sa.String(10), nullable=False),
        sa.Column("ai_recommendation", sa.String(10), nullable=True),
        sa.Column("is_override", sa.Boolean(), nullable=False, server_default="FALSE"),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("idx_reviews_campaign", "reviews", ["campaign_id"])
    op.create_index("idx_reviews_is_override", "reviews", ["is_override"])
    op.create_index("idx_reviews_reviewed_at", "reviews", ["reviewed_at"])

    # ------------------------------------------------------------------
    # audit_logs
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("actor", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("idx_audit_campaign", "audit_logs", ["campaign_id"])
    op.create_index("idx_audit_event_type", "audit_logs", ["event_type"])
    op.create_index("idx_audit_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    # Drop in reverse order to respect foreign key constraints
    op.drop_table("audit_logs")
    op.drop_table("reviews")
    op.drop_table("ai_analyses")
    op.drop_table("campaigns")
