"""Expand the default event categories.

Revision ID: c4d7a82f91be
Revises: 81e593c3855c
Create Date: 2026-08-13

"""

from alembic import op
import sqlalchemy as sa


revision = "c4d7a82f91be"
down_revision = "81e593c3855c"
branch_labels = None
depends_on = None


def upgrade():
    categories = sa.table(
        "categories",
        sa.column("name", sa.String(length=50)),
    )
    op.execute(
        categories.update()
        .where(categories.c.name == "Technology")
        .values(name="Technology & Gaming")
    )
    op.execute(categories.insert().values(name="Other"))


def downgrade():
    categories = sa.table(
        "categories",
        sa.column("name", sa.String(length=50)),
    )
    op.execute(categories.delete().where(categories.c.name == "Other"))
    op.execute(
        categories.update()
        .where(categories.c.name == "Technology & Gaming")
        .values(name="Technology")
    )
