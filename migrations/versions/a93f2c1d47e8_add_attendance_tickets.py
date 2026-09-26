"""Add attendee QR tickets and check-in state.

Revision ID: a93f2c1d47e8
Revises: f6c31e8a02d4
Create Date: 2026-08-16
"""

import secrets

from alembic import op
import sqlalchemy as sa


revision = "a93f2c1d47e8"
down_revision = "f6c31e8a02d4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("attendance") as batch_op:
        batch_op.add_column(sa.Column("ticket_token", sa.String(length=64)))
        batch_op.add_column(sa.Column("checked_in_at", sa.DateTime()))

    attendance = sa.table(
        "attendance",
        sa.column("user_id", sa.Integer),
        sa.column("event_id", sa.Integer),
        sa.column("ticket_token", sa.String),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(attendance.c.user_id, attendance.c.event_id)
    ).all()
    for row in rows:
        connection.execute(
            attendance.update()
            .where(
                attendance.c.user_id == row.user_id,
                attendance.c.event_id == row.event_id,
            )
            .values(ticket_token=secrets.token_urlsafe(18))
        )

    with op.batch_alter_table("attendance") as batch_op:
        batch_op.alter_column("ticket_token", nullable=False)
        batch_op.create_unique_constraint(
            "uq_attendance_ticket_token", ["ticket_token"]
        )


def downgrade():
    with op.batch_alter_table("attendance") as batch_op:
        batch_op.drop_constraint("uq_attendance_ticket_token", type_="unique")
        batch_op.drop_column("checked_in_at")
        batch_op.drop_column("ticket_token")
