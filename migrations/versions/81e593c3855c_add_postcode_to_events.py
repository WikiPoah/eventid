"""add postcode to events

Revision ID: 81e593c3855c
Revises: 4e7d8b9c0a12
Create Date: 2026-08-09 00:18:33.341350

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "81e593c3855c"
down_revision = "4e7d8b9c0a12"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("events") as batch_op:
        batch_op.add_column(
            sa.Column(
                "postcode",
                sa.String(length=20),
                nullable=True,
            )
        )

    # Give existing events a placeholder postcode.
    op.execute(
        "UPDATE events SET postcode = 'UNKNOWN' WHERE postcode IS NULL"
    )

    with op.batch_alter_table("events") as batch_op:
        batch_op.alter_column(
            "postcode",
            existing_type=sa.String(length=20),
            nullable=False,
        )


def downgrade():
    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_column("postcode")