"""Transactional, versioned provisional learner-state applications."""
from alembic import op
import sqlalchemy as sa

revision = "0010_state_application"
down_revision = "0009_attempts"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("whole_task_evidence_count", "part_task_evidence_count", "whole_task_attempt_count",
                 "whole_task_points", "whole_task_max_points"):
        op.add_column("learner_skill_states", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
        op.alter_column("learner_skill_states", name, existing_type=sa.Integer(), server_default=None)
    op.add_column("learner_skill_states", sa.Column("policy_version", sa.String(64), nullable=True))
    op.drop_constraint("ck_state_initial_unknown", "learner_skill_states", type_="check")
    op.create_check_constraint("ck_state_observed", "learner_skill_states",
        "(band = 'unknown' AND evidence_count = 0 AND revision = 0 AND policy_version IS NULL) OR "
        "(band IN ('developing', 'secure') AND evidence_count > 0 AND revision > 0 AND policy_version IS NOT NULL)")
    op.create_check_constraint("ck_state_counts", "learner_skill_states",
        "evidence_count = whole_task_evidence_count + part_task_evidence_count AND "
        "whole_task_evidence_count >= whole_task_attempt_count AND whole_task_attempt_count >= 0 AND "
        "part_task_evidence_count >= 0 AND evidence_count >= revision AND "
        "whole_task_points >= 0 AND whole_task_max_points >= whole_task_points AND "
        "((whole_task_attempt_count = 0 AND whole_task_max_points = 0) OR "
        "(whole_task_attempt_count > 0 AND whole_task_max_points > 0))")
    op.create_check_constraint("ck_state_secure", "learner_skill_states",
        "band <> 'secure' OR (whole_task_attempt_count >= 2 AND whole_task_points * 5 >= whole_task_max_points * 4)")
    op.create_unique_constraint("uq_attempt_id_enrollment_domain", "attempts", ["id", "enrollment_id", "domain_version_id"])
    op.create_table("state_applications",
        sa.Column("attempt_id", sa.String(36), sa.ForeignKey("attempt_scores.attempt_id"), primary_key=True),
        sa.Column("enrollment_id", sa.String(36), nullable=False),
        sa.Column("domain_version_id", sa.String(36), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("formal_certification", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id", "enrollment_id", "domain_version_id"],
            ["attempts.id", "attempts.enrollment_id", "attempts.domain_version_id"],
            name="fk_application_attempt_enrollment_domain"),
        sa.CheckConstraint("formal_certification = 0", name="ck_application_provisional"),
        mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci")


def downgrade():
    # MySQL DDL auto-commits: refuse before changing anything rather than silently
    # discarding observed state to restore Day 9's initial-only constraint.
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM learner_skill_states WHERE revision <> 0")):
        raise RuntimeError("Cannot downgrade observed learner state; restore a pre-Day-10 backup instead")
    op.drop_table("state_applications")
    op.drop_constraint("uq_attempt_id_enrollment_domain", "attempts", type_="unique")
    for name in ("ck_state_secure", "ck_state_counts", "ck_state_observed"):
        op.drop_constraint(name, "learner_skill_states", type_="check")
    op.create_check_constraint("ck_state_initial_unknown", "learner_skill_states",
                               "band = 'unknown' AND evidence_count = 0 AND revision = 0")
    for name in ("policy_version", "whole_task_max_points", "whole_task_points", "whole_task_attempt_count",
                 "part_task_evidence_count", "whole_task_evidence_count"):
        op.drop_column("learner_skill_states", name)
