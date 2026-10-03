"""Add draft domain versions, competencies, and classified skills."""
from alembic import op
import sqlalchemy as sa

revision = "0003_domain_authoring"
down_revision = "0002_course_lifecycle"
branch_labels = None
depends_on = None

TABLE_OPTIONS = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


def upgrade():
    op.create_table(
        "domain_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("course_id", "version", name="uq_domain_course_version"),
        sa.CheckConstraint("version > 0", name="ck_domain_positive_version"),
        sa.CheckConstraint("status IN ('draft', 'published')", name="ck_domain_status"),
        **TABLE_OPTIONS,
    )
    op.create_table(
        "competencies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("domain_version_id", sa.String(36), sa.ForeignKey("domain_versions.id"), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("domain_version_id", "code", name="uq_competency_domain_code"),
        sa.UniqueConstraint("id", "domain_version_id", name="uq_competency_id_domain"),
        **TABLE_OPTIONS,
    )
    op.create_table(
        "skills",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("domain_version_id", sa.String(36), sa.ForeignKey("domain_versions.id"), nullable=False),
        sa.Column("competency_id", sa.String(36), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("skill_kind", sa.String(16), nullable=False),
        sa.Column("requires_automaticity", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["competency_id", "domain_version_id"],
                                ["competencies.id", "competencies.domain_version_id"],
                                name="fk_skill_competency_domain"),
        sa.UniqueConstraint("domain_version_id", "code", name="uq_skill_domain_code"),
        sa.UniqueConstraint("id", "domain_version_id", name="uq_skill_id_domain"),
        sa.CheckConstraint("skill_kind IN ('routine', 'non_routine')", name="ck_skill_kind"),
        sa.CheckConstraint("requires_automaticity IN (0, 1)", name="ck_skill_automaticity_boolean"),
        sa.CheckConstraint("skill_kind = 'routine' OR requires_automaticity = 0", name="ck_skill_automaticity_routine"),
        **TABLE_OPTIONS,
    )


def downgrade():
    op.drop_table("skills")
    op.drop_table("competencies")
    op.drop_table("domain_versions")
