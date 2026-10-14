"""Context generations, unscored completion and separate experimental reminders."""
from alembic import op
import sqlalchemy as sa

revision = "0011_continuity"
down_revision = "0010_state_application"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("activity_generations", sa.Column("context_variant", sa.String(64), nullable=False,
                                                  server_default="positive-sales-v1"))
    op.alter_column("activity_generations", "context_variant", existing_type=sa.String(64), server_default=None)
    op.create_unique_constraint("uq_generation_plan_version_context", "activity_generations",
                                ["loop_plan_id", "generator_version", "context_variant"])
    op.drop_constraint("uq_generation_plan_version", "activity_generations", type_="unique")
    op.create_check_constraint("ck_generation_context", "activity_generations",
        "context_variant = template_version AND context_variant IN ('positive-sales-v1', 'positive-donations-v1')")
    op.create_table("activity_completions",
        sa.Column("activity_id", sa.String(36), sa.ForeignKey("activities.id"), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci")
    op.create_table("review_schedules",
        sa.Column("enrollment_id", sa.String(36), primary_key=True),
        sa.Column("skill_id", sa.String(36), primary_key=True),
        sa.Column("domain_version_id", sa.String(36), nullable=False),
        sa.Column("source_attempt_id", sa.String(36), sa.ForeignKey("attempt_scores.attempt_id"), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["enrollment_id", "skill_id"],
            ["learner_skill_states.enrollment_id", "learner_skill_states.skill_id"], name="fk_review_state"),
        sa.ForeignKeyConstraint(["source_attempt_id", "enrollment_id", "domain_version_id"],
            ["attempts.id", "attempts.enrollment_id", "attempts.domain_version_id"], name="fk_review_attempt_enrollment_domain"),
        sa.ForeignKeyConstraint(["skill_id", "domain_version_id"],
            ["skills.id", "skills.domain_version_id"], name="fk_review_skill_domain"),
        sa.CheckConstraint("policy_version = 'experimental-review-v1' AND due_at > scheduled_at", name="ck_review_policy_due"),
        mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci")


def downgrade():
    # MySQL DDL auto-commits. Refuse before touching anything if continuity would be lost.
    bind = op.get_bind()
    if (bind.scalar(sa.text("SELECT COUNT(*) FROM activity_completions"))
            or bind.scalar(sa.text("SELECT COUNT(*) FROM review_schedules"))
            or bind.scalar(sa.text("SELECT COUNT(*) FROM activity_generations WHERE context_variant <> 'positive-sales-v1'"))):
        raise RuntimeError("Cannot downgrade retained continuity data; restore a pre-Day-11 backup instead")
    op.drop_table("review_schedules")
    op.drop_table("activity_completions")
    op.drop_constraint("ck_generation_context", "activity_generations", type_="check")
    op.create_unique_constraint("uq_generation_plan_version", "activity_generations", ["loop_plan_id", "generator_version"])
    op.drop_constraint("uq_generation_plan_version_context", "activity_generations", type_="unique")
    op.drop_column("activity_generations", "context_variant")
