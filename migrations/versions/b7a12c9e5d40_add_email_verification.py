"""Add email verification timestamp.

Revision ID: b7a12c9e5d40
Revises: d39b6fa2e715
Create Date: 2026-08-17
"""

from alembic import op
import sqlalchemy as sa


revision = "b7a12c9e5d40"
down_revision = "d39b6fa2e715"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("email_verified_at", sa.DateTime()))


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("email_verified_at")
