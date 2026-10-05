"""Add same-version prerequisite edges and publication metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0004_domain_publishing"
down_revision = "0003_domain_authoring"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("domain_versions", sa.Column("published_at", sa.DateTime(), nullable=True))
    # Day 3 reserved the status; preserve any pre-existing manually published rows.
    op.execute("UPDATE domain_versions SET published_at = created_at WHERE status = 'published'")
    op.create_check_constraint("ck_domain_publication", "domain_versions",
                               "(status = 'draft' AND published_at IS NULL) OR "
                               "(status = 'published' AND published_at IS NOT NULL)")
    op.create_table(
        "skill_prerequisites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("domain_version_id", sa.String(36), sa.ForeignKey("domain_versions.id"), nullable=False),
        sa.Column("skill_id", sa.String(36), nullable=False),
        sa.Column("prerequisite_skill_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["skill_id", "domain_version_id"], ["skills.id", "skills.domain_version_id"],
                                name="fk_prerequisite_skill_domain"),
        sa.ForeignKeyConstraint(["prerequisite_skill_id", "domain_version_id"], ["skills.id", "skills.domain_version_id"],
                                name="fk_prerequisite_required_domain"),
        sa.UniqueConstraint("domain_version_id", "skill_id", "prerequisite_skill_id", name="uq_prerequisite_edge"),
        sa.CheckConstraint("skill_id <> prerequisite_skill_id", name="ck_prerequisite_not_self"),
        mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade():
    op.drop_table("skill_prerequisites")
    op.drop_constraint("ck_domain_publication", "domain_versions", type_="check")
    op.drop_column("domain_versions", "published_at")
