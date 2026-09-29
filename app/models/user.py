from datetime import UTC, datetime

from app.database.db import db


class User(db.Model):
    """Account identity that owns events and records attendance separately."""

    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)

    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)

    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    # Bumping this version invalidates existing cookies and signed email links.
    auth_version = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    username_changed_at = db.Column(db.DateTime)
    email_changed_at = db.Column(db.DateTime)
    email_verified_at = db.Column(db.DateTime)

    profile_picture_path = db.Column(db.String(255))
    bio = db.Column(db.Text)

    country = db.Column(db.String(100))
    city = db.Column(db.String(100))

    # Organiser is a profile label, not a role gate: management checks ownership.
    is_organiser = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    events = db.relationship("Event", back_populates="organiser")

    attendances = db.relationship(
        "Attendance", back_populates="user", cascade="all, delete-orphan"
    )

    # Provide read-only event access while retaining attendance records
    attending_events = db.relationship("Event", secondary="attendance", viewonly=True)

    favourites = db.relationship(
        "Favourite", back_populates="user", cascade="all, delete-orphan"
    )
    favourite_events = db.relationship("Event", secondary="favourites", viewonly=True)

    sessions = db.relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )
    security_events = db.relationship(
        "SecurityEvent", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User {self.username}>"
