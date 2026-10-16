"""Retain provider/model/prompt provenance without changing existing content hashes."""
from alembic import op
import sqlalchemy as sa

revision = "0012_generation_providers"
down_revision = "0011_continuity"
branch_labels = None
depends_on = None


def upgrade():
    for name, kind, default in [("provider", sa.String(16), "template"),
                                ("prompt_version", sa.String(64), "template-instructions-v1")]:
        op.add_column("activity_generations", sa.Column(name, kind, nullable=False, server_default=default))
        op.alter_column("activity_generations", name, existing_type=kind, server_default=None)
    op.add_column("activity_generations", sa.Column("model", sa.String(128), nullable=True))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM activity_generations WHERE provider <> 'template'")):
        raise RuntimeError("Cannot discard retained AI provenance; restore a pre-Day-12 backup instead")
    for name in ["model", "prompt_version", "provider"]:
        op.drop_column("activity_generations", name)
