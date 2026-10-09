"""Frozen template activities with attributed sequence review and plan-step lineage."""
from alembic import op
import sqlalchemy as sa

revision = "0008_generation"
down_revision = "0007_planner"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "activity_generations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("loop_plan_id", sa.String(36), sa.ForeignKey("loop_plans.id"), nullable=False),
        sa.Column("generator_version", sa.String(64), nullable=False),
        sa.Column("template_version", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(128, collation="utf8mb4_bin"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("review_status", sa.String(16), nullable=False),
        sa.Column("review_scope", sa.String(32), nullable=False),
        sa.Column("reviewed_by", sa.String(128, collation="utf8mb4_bin"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.UniqueConstraint("loop_plan_id", "generator_version", name="uq_generation_plan_version"),
        sa.UniqueConstraint("id", "loop_plan_id", name="uq_generation_id_plan"),
        sa.CheckConstraint("review_status IN ('draft', 'approved', 'rejected')", name="ck_generation_status"),
        sa.CheckConstraint("review_scope = 'synthetic_only'", name="ck_generation_scope"),
        sa.CheckConstraint("(review_status = 'draft' AND reviewed_by IS NULL AND reviewed_at IS NULL AND review_note IS NULL) OR "
                           "(review_status IN ('approved', 'rejected') AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL "
                           "AND review_note IS NOT NULL AND reviewed_by <> created_by)", name="ck_generation_review"),
        mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_table(
        "activities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("generation_id", sa.String(36), nullable=False),
        sa.Column("loop_plan_id", sa.String(36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["generation_id", "loop_plan_id"], ["activity_generations.id", "activity_generations.loop_plan_id"], name="fk_activity_generation_plan"),
        sa.ForeignKeyConstraint(["loop_plan_id", "position"], ["loop_steps.loop_plan_id", "loop_steps.position"], name="fk_activity_plan_step"),
        sa.UniqueConstraint("generation_id", "position", name="uq_activity_generation_step"),
        sa.CheckConstraint("position > 0", name="ck_activity_position"),
        mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade():
    op.drop_table("activities")
    op.drop_table("activity_generations")
