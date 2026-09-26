"""Add private invitations and registration deadlines.

Revision ID: f6c31e8a02d4
Revises: e5b92d734ac1
Create Date: 2026-08-15

"""

from alembic import op
import sqlalchemy as sa


revision = "f6c31e8a02d4"
down_revision = "e5b92d734ac1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("events") as batch_op:
        batch_op.add_column(sa.Column("registration_deadline", sa.DateTime()))
        batch_op.add_column(sa.Column("invite_token", sa.String(length=128)))
        batch_op.add_column(sa.Column("invite_expires_at", sa.DateTime()))
        batch_op.add_column(sa.Column("invited_emails", sa.Text()))
        batch_op.add_column(
            sa.Column("requests_open", sa.Boolean(), server_default=sa.true(), nullable=False)
        )
        batch_op.create_unique_constraint("uq_events_invite_token", ["invite_token"])


def downgrade():
    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_constraint("uq_events_invite_token", type_="unique")
        batch_op.drop_column("requests_open")
        batch_op.drop_column("invited_emails")
        batch_op.drop_column("invite_expires_at")
        batch_op.drop_column("invite_token")
        batch_op.drop_column("registration_deadline")
