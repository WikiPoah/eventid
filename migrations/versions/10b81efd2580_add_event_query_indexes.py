"""add event query indexes

Revision ID: 10b81efd2580
Revises: 6f80a76130a3
Create Date: 2026-08-03 22:23:30.036569

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '10b81efd2580'
down_revision = '6f80a76130a3'
branch_labels = None
depends_on = None


def upgrade():
    # Add composite indexes that match discovery and dashboard query ordering
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.create_index(
            'ix_events_organiser_start_datetime',
            ['organiser_id', 'start_datetime'],
            unique=False,
        )
        batch_op.create_index(
            'ix_events_privacy_city',
            ['privacy', 'city'],
            unique=False,
        )
        batch_op.create_index(
            'ix_events_privacy_start_datetime',
            ['privacy', 'start_datetime'],
            unique=False,
        )


def downgrade():
    # Remove the query indexes without changing event data
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_index('ix_events_privacy_start_datetime')
        batch_op.drop_index('ix_events_privacy_city')
        batch_op.drop_index('ix_events_organiser_start_datetime')
