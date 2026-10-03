"""Preserve existing courses and add ownership and archival metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0002_course_lifecycle"
down_revision = "0001_courses"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("courses", sa.Column("created_by", sa.String(128), nullable=True))
    op.add_column("courses", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("courses", sa.Column("archived_at", sa.DateTime(), nullable=True))
    # The Day 1 key becomes the same stable author for every pre-existing course.
    op.execute("UPDATE courses SET created_by = 'dev-author', updated_at = created_at")
    op.alter_column("courses", "created_by", existing_type=sa.String(128), nullable=False)
    op.alter_column("courses", "updated_at", existing_type=sa.DateTime(), nullable=False)


def downgrade():
    op.drop_column("courses", "archived_at")
    op.drop_column("courses", "updated_at")
    op.drop_column("courses", "created_by")
