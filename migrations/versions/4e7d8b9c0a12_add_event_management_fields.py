"""add event management fields

Revision ID: 4e7d8b9c0a12
Revises: 10b81efd2580
Create Date: 2026-08-03 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "4e7d8b9c0a12"
down_revision = "10b81efd2580"
branch_labels = None
depends_on = None


def upgrade():
    # Add optional image metadata and constrain supported lifecycle states
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("image_path", sa.String(length=255), nullable=True)
        )
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=20),
            nullable=False,
            server_default="Draft",
        )
        batch_op.create_check_constraint(
            "ck_events_status",
            "status IN ('Draft', 'Published', 'Cancelled')",
        )


def downgrade():
    # Remove v0.9 fields while preserving all pre-existing event data
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.drop_constraint("ck_events_status", type_="check")
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=20),
            nullable=False,
            server_default=None,
        )
        batch_op.drop_column("image_path")
