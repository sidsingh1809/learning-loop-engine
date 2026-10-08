"""Persist reproducible decisions and connected steps without changing learner state."""
from alembic import op
import sqlalchemy as sa

revision = "0007_planner"
down_revision = "0006_catalog"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "loop_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("enrollment_id", sa.String(36), nullable=False),
        sa.Column("domain_version_id", sa.String(36), nullable=False),
        sa.Column("target_skill_id", sa.String(36), nullable=False),
        sa.Column("focus_skill_id", sa.String(36), nullable=False),
        sa.Column("learning_science_policy_id", sa.String(36), sa.ForeignKey("policy_versions.id"), nullable=False),
        sa.Column("safety_policy_id", sa.String(36), sa.ForeignKey("policy_versions.id"), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("time_budget_minutes", sa.Integer(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["enrollment_id", "domain_version_id"], ["enrollments.id", "enrollments.domain_version_id"], name="fk_plan_enrollment_domain"),
        sa.ForeignKeyConstraint(["target_skill_id", "domain_version_id"], ["skills.id", "skills.domain_version_id"], name="fk_plan_target_domain"),
        sa.ForeignKeyConstraint(["focus_skill_id", "domain_version_id"], ["skills.id", "skills.domain_version_id"], name="fk_plan_focus_domain"),
        sa.UniqueConstraint("enrollment_id", "input_fingerprint", name="uq_plan_enrollment_input"),
        sa.UniqueConstraint("id", "domain_version_id", name="uq_plan_id_domain"),
        sa.CheckConstraint("time_budget_minutes > 0 AND time_budget_minutes <= 180", name="ck_plan_budget"),
        sa.CheckConstraint("estimated_minutes > 0 AND estimated_minutes <= time_budget_minutes", name="ck_plan_duration"),
        mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_table(
        "loop_steps",
        sa.Column("loop_plan_id", sa.String(36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("domain_version_id", sa.String(36), nullable=False),
        sa.Column("skill_id", sa.String(36), nullable=False),
        sa.Column("activity_variant_id", sa.String(36), sa.ForeignKey("activity_variants.id"), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column("support_level", sa.String(16), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["loop_plan_id", "domain_version_id"], ["loop_plans.id", "loop_plans.domain_version_id"], name="fk_step_plan_domain"),
        sa.ForeignKeyConstraint(["skill_id", "domain_version_id"], ["skills.id", "skills.domain_version_id"], name="fk_step_skill_domain"),
        sa.CheckConstraint("position > 0", name="ck_step_position"),
        sa.CheckConstraint("estimated_minutes > 0 AND estimated_minutes <= 180", name="ck_step_duration"),
        sa.CheckConstraint("support_level IN ('high', 'minimal')", name="ck_step_support"),
        sa.CheckConstraint("role IN ('whole_task_context', 'focus_practice', 'whole_task_return', 'whole_task')", name="ck_step_role"),
        mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade():
    op.drop_table("loop_steps")
    op.drop_table("loop_plans")
