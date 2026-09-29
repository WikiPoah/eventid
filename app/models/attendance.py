import secrets
from datetime import UTC, datetime

from app.database.db import db


class Attendance(db.Model):
    """One registration per user/event, enforced by the composite primary key.

    Only Going consumes capacity or enables tickets/check-in. Private requests
    can instead be Pending, Declined or Revoked without claiming a seat.
    """

    __tablename__ = "attendance"

    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), primary_key=True)

    event_id = db.Column(db.Integer, db.ForeignKey("events.event_id"), primary_key=True)

    registered_at = db.Column(
        db.DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    status = db.Column(db.String(20), nullable=False, default="Going")

    # A token exists even while pending; routes require Going before exposing
    # the ticket or accepting it for check-in. Possession alone is not authority.
    ticket_token = db.Column(
        db.String(64),
        unique=True,
        nullable=False,
        default=lambda: secrets.token_urlsafe(18),
    )

    checked_in_at = db.Column(db.DateTime)

    user = db.relationship("User", back_populates="attendances")

    event = db.relationship("Event", back_populates="attendees")

    def __repr__(self):

        return f"<Attendance User {self.user_id} Event {self.event_id}>"
