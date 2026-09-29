"""Add identity change cooldown timestamps.

Revision ID: d39b6fa2e715
Revises: c28a5e91d604
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa


revision = "d39b6fa2e715"
down_revision = "c28a5e91d604"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("username_changed_at", sa.DateTime()))
        batch_op.add_column(sa.Column("email_changed_at", sa.DateTime()))


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("email_changed_at")
        batch_op.drop_column("username_changed_at")
