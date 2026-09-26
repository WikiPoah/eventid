from datetime import UTC, datetime

from app.database.db import db


class Favourite(db.Model):
    """Store an event saved by a user for later."""

    __tablename__ = "favourites"

    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.event_id"), primary_key=True)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    user = db.relationship("User", back_populates="favourites")
    event = db.relationship("Event", back_populates="favourites")
