"""Pseudonymous learners, version-bound enrollments and unknown initial states."""
from alembic import op
import sqlalchemy as sa

revision = "0005_learners"
down_revision = "0004_domain_publishing"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_domain_id_course", "domain_versions", ["id", "course_id"])
    op.create_table(
        "learners",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("principal_subject", sa.String(128, collation="utf8mb4_bin"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_table(
        "enrollments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id"), nullable=False),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("domain_version_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["domain_version_id", "course_id"], ["domain_versions.id", "domain_versions.course_id"],
                                name="fk_enrollment_domain_course"),
        sa.UniqueConstraint("learner_id", "course_id", name="uq_enrollment_learner_course"),
        sa.UniqueConstraint("id", "domain_version_id", name="uq_enrollment_id_domain"),
        sa.CheckConstraint("status = 'active'", name="ck_enrollment_status"),
        mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_table(
        "learner_skill_states",
        sa.Column("enrollment_id", sa.String(36), primary_key=True),
        sa.Column("skill_id", sa.String(36), primary_key=True),
        sa.Column("domain_version_id", sa.String(36), nullable=False),
        sa.Column("band", sa.String(16), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["enrollment_id", "domain_version_id"], ["enrollments.id", "enrollments.domain_version_id"],
                                name="fk_state_enrollment_domain"),
        sa.ForeignKeyConstraint(["skill_id", "domain_version_id"], ["skills.id", "skills.domain_version_id"],
                                name="fk_state_skill_domain"),
        sa.CheckConstraint("band = 'unknown' AND evidence_count = 0 AND revision = 0", name="ck_state_initial_unknown"),
        mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade():
    op.drop_table("learner_skill_states")
    op.drop_table("enrollments")
    op.drop_table("learners")
    op.drop_constraint("uq_domain_id_course", "domain_versions", type_="unique")
