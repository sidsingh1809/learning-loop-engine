"""Immutable submitted answers, terminal scores and criterion-level evidence."""
from alembic import op
import sqlalchemy as sa

revision = "0009_attempts"
down_revision = "0008_generation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_activity_id_plan", "activities", ["id", "loop_plan_id"])
    op.create_unique_constraint("uq_plan_id_enrollment_domain", "loop_plans", ["id", "enrollment_id", "domain_version_id"])
    op.create_table(
        "attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("activity_id", sa.String(36), nullable=False),
        sa.Column("loop_plan_id", sa.String(36), nullable=False),
        sa.Column("enrollment_id", sa.String(36), nullable=False),
        sa.Column("domain_version_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(36), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("scoring_method", sa.String(32), nullable=False),
        sa.Column("submitted_by", sa.String(128, collation="utf8mb4_bin"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["activity_id", "loop_plan_id"], ["activities.id", "activities.loop_plan_id"], name="fk_attempt_activity_plan"),
        sa.ForeignKeyConstraint(["loop_plan_id", "enrollment_id", "domain_version_id"],
                                ["loop_plans.id", "loop_plans.enrollment_id", "loop_plans.domain_version_id"], name="fk_attempt_plan_enrollment_domain"),
        sa.UniqueConstraint("enrollment_id", "idempotency_key", name="uq_attempt_enrollment_key"),
        sa.UniqueConstraint("id", "domain_version_id", name="uq_attempt_id_domain"),
        sa.CheckConstraint("scoring_method IN ('selected_response', 'instructor_review')", name="ck_attempt_method"),
        mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_table(
        "attempt_scores",
        sa.Column("attempt_id", sa.String(36), sa.ForeignKey("attempts.id"), primary_key=True),
        sa.Column("scoring_method", sa.String(32), nullable=False),
        sa.Column("scorer_version", sa.String(64), nullable=False),
        sa.Column("rubric_version", sa.String(64), nullable=False),
        sa.Column("review_scope", sa.String(32), nullable=False),
        sa.Column("reviewed_by", sa.String(128, collation="utf8mb4_bin"), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("(scoring_method = 'selected_response' AND reviewed_by IS NULL AND review_note IS NULL) OR "
                           "(scoring_method = 'instructor_review' AND reviewed_by IS NOT NULL AND review_note IS NOT NULL)", name="ck_score_attribution"),
        sa.CheckConstraint("review_scope = 'synthetic_only'", name="ck_score_scope"),
        mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_table(
        "evidence",
        sa.Column("attempt_id", sa.String(36), sa.ForeignKey("attempt_scores.attempt_id"), primary_key=True),
        sa.Column("criterion_code", sa.String(32, collation="utf8mb4_bin"), primary_key=True),
        sa.Column("domain_version_id", sa.String(36), nullable=False),
        sa.Column("skill_id", sa.String(36), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("max_points", sa.Integer(), nullable=False),
        sa.Column("evidence_kind", sa.String(16), nullable=False),
        sa.Column("evidence_tier", sa.String(16), nullable=False),
        sa.Column("formal_certification", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id", "domain_version_id"], ["attempts.id", "attempts.domain_version_id"], name="fk_evidence_attempt_domain"),
        sa.ForeignKeyConstraint(["skill_id", "domain_version_id"], ["skills.id", "skills.domain_version_id"], name="fk_evidence_skill_domain"),
        sa.CheckConstraint("max_points > 0 AND points >= 0 AND points <= max_points", name="ck_evidence_points"),
        sa.CheckConstraint("evidence_kind IN ('part_task', 'whole_task')", name="ck_evidence_kind"),
        sa.CheckConstraint("evidence_tier = 'provisional' AND formal_certification = 0", name="ck_evidence_provisional"),
        mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade():
    op.drop_table("evidence")
    op.drop_table("attempt_scores")
    op.drop_table("attempts")
    op.drop_constraint("uq_activity_id_plan", "activities", type_="unique")
    op.drop_constraint("uq_plan_id_enrollment_domain", "loop_plans", type_="unique")
