"""Add user authentication version.

Revision ID: c28a5e91d604
Revises: a93f2c1d47e8
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa


revision = "c28a5e91d604"
down_revision = "a93f2c1d47e8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "auth_version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("auth_version")
