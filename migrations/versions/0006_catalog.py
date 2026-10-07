"""Versioned prototype activity/policy catalog and attributed review."""
from alembic import op
import sqlalchemy as sa

revision = "0006_catalog"
down_revision = "0005_learners"
branch_labels = None
depends_on = None


def reviewed_columns():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("created_by", sa.String(128, collation="utf8mb4_bin"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("review_status", sa.String(16), nullable=False),
        sa.Column("review_scope", sa.String(32), nullable=False),
        sa.Column("reviewed_by", sa.String(128, collation="utf8mb4_bin"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("references", sa.JSON(), nullable=False),
    ]


def reviewed_constraints(prefix):
    return [
        sa.CheckConstraint("version > 0", name="ck_" + prefix + "_version"),
        sa.CheckConstraint("review_status IN ('draft', 'approved', 'rejected')", name="ck_" + prefix + "_status"),
        sa.CheckConstraint("review_scope = 'synthetic_only'", name="ck_" + prefix + "_scope"),
        sa.CheckConstraint("(review_status = 'draft' AND reviewed_by IS NULL AND reviewed_at IS NULL AND review_note IS NULL) OR "
                           "(review_status IN ('approved', 'rejected') AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL "
                           "AND review_note IS NOT NULL AND reviewed_by <> created_by)", name="ck_" + prefix + "_review"),
    ]


def upgrade():
    op.create_table(
        "policy_versions", *reviewed_columns(),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.UniqueConstraint("category", "code", "version", name="uq_policy_category_code_version"),
        sa.CheckConstraint("category IN ('learning_science', 'safety')", name="ck_policy_category"),
        *reviewed_constraints("policy"),
        mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_table(
        "activity_variants", *reviewed_columns(),
        sa.Column("activity_type", sa.String(32), nullable=False),
        sa.Column("evidence_tier", sa.String(16), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("guidance", sa.Text(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("learning_science_policy_id", sa.String(36), sa.ForeignKey("policy_versions.id"), nullable=False),
        sa.Column("safety_policy_id", sa.String(36), sa.ForeignKey("policy_versions.id"), nullable=False),
        sa.UniqueConstraint("code", "version", name="uq_activity_code_version"),
        sa.CheckConstraint("activity_type IN ('worked_example', 'selected_response', 'constructed_response')", name="ck_activity_type"),
        sa.CheckConstraint("evidence_tier = 'provisional'", name="ck_activity_evidence_tier"),
        sa.CheckConstraint("estimated_minutes > 0 AND estimated_minutes <= 180", name="ck_activity_minutes"),
        *reviewed_constraints("activity"),
        mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_table(
        "component_activity_mappings",
        sa.Column("activity_variant_id", sa.String(36), sa.ForeignKey("activity_variants.id"), primary_key=True),
        sa.Column("component", sa.String(32), primary_key=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.CheckConstraint("component IN ('learning_tasks', 'supportive_information', 'procedural_information', 'part_task_practice')",
                           name="ck_mapping_component"),
        mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade():
    op.drop_table("component_activity_mappings")
    op.drop_table("activity_variants")
    op.drop_table("policy_versions")
