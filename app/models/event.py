from datetime import UTC, datetime

from app.database.db import db


class Event(db.Model):
    """An organiser-owned event with lifecycle, access and capacity settings."""

    __tablename__ = "events"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('Draft', 'Published', 'Cancelled')",
            name="ck_events_status",
        ),
        db.Index(
            "ix_events_privacy_start_datetime",
            "privacy",
            "start_datetime",
        ),
        db.Index("ix_events_privacy_city", "privacy", "city"),
        db.Index(
            "ix_events_organiser_start_datetime",
            "organiser_id",
            "start_datetime",
        ),
    )

    event_id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)

    venue_name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    postcode = db.Column(db.String(20), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    country = db.Column(db.String(100), nullable=False)
    location_notes = db.Column(db.Text)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    start_datetime = db.Column(db.DateTime, nullable=False)
    end_datetime = db.Column(db.DateTime, nullable=False)

    status = db.Column(
        db.String(20),
        nullable=False,
        default="Draft",
        server_default="Draft",
    )

    privacy = db.Column(db.String(20), nullable=False, default="Private")

    capacity = db.Column(db.Integer)
    registration_deadline = db.Column(db.DateTime)

    # Private events use expiring invite links and optional email restrictions.
    invite_token = db.Column(db.String(128), unique=True)
    invite_expires_at = db.Column(db.DateTime)
    invited_emails = db.Column(db.Text)
    requests_open = db.Column(db.Boolean, nullable=False, default=True)

    # Generated relative name only; routes authorize access through the event.
    image_path = db.Column(db.String(255))

    organiser_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    organiser = db.relationship("User", back_populates="events")

    event_categories = db.relationship(
        "EventCategory", back_populates="event", cascade="all, delete-orphan"
    )

    # Provide read-only category access while retaining association records
    categories = db.relationship(
        "Category", secondary="event_categories", viewonly=True
    )

    attendees = db.relationship(
        "Attendance", back_populates="event", cascade="all, delete-orphan"
    )

    # Provide read-only user access without treating organisers as attendees
    attending_users = db.relationship("User", secondary="attendance", viewonly=True)

    favourites = db.relationship(
        "Favourite", back_populates="event", cascade="all, delete-orphan"
    )
    favourited_by = db.relationship("User", secondary="favourites", viewonly=True)

    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self):
        return f"<Event {self.title}>"
