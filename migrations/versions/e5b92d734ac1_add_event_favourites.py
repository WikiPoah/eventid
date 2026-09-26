"""Add event favourites.

Revision ID: e5b92d734ac1
Revises: c4d7a82f91be
Create Date: 2026-08-13

"""

from alembic import op
import sqlalchemy as sa


revision = "e5b92d734ac1"
down_revision = "c4d7a82f91be"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "favourites",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.event_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("user_id", "event_id"),
    )


def downgrade():
    op.drop_table("favourites")
