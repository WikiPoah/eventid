from datetime import datetime

from app.database.db import db


# Store all information related to an event
class Event(db.Model):

    __tablename__ = "events"

    # Uniquely identify each event
    event_id = db.Column(db.Integer, primary_key=True)

    # Store the event's main details
    title = db.Column(db.String(100), nullable=False)

    description = db.Column(db.Text, nullable=False)

    # Store the event's location information
    venue_name = db.Column(db.String(100), nullable=False)

    address = db.Column(db.String(255), nullable=False)

    city = db.Column(db.String(100), nullable=False)

    country = db.Column(db.String(100), nullable=False)

    location_notes = db.Column(db.Text)

    latitude = db.Column(db.Float)

    longitude = db.Column(db.Float)

    # Store when the event takes place and its current visibility
    start_datetime = db.Column(db.DateTime, nullable=False)

    end_datetime = db.Column(db.DateTime, nullable=False)

    status = db.Column(db.String(20), nullable=False, default="Draft")

    privacy = db.Column(db.String(20), nullable=False, default="Private")

    # Store the maximum number of attendees if a limit is set
    capacity = db.Column(db.Integer)

    # Link each event to its organiser
    organiser_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id"),
        nullable=False
    )

    organiser = db.relationship(
        "User",
        back_populates="events"
    )

    # Link events to their assigned categories
    categories = db.relationship(
        "EventCategory",
        back_populates="event",
        cascade="all, delete-orphan"
    )

    # Track users who have registered for the event
    attendees = db.relationship(
        "Attendance",
        back_populates="event",
        cascade="all, delete-orphan"
    )

    # Record when the event was created and last updated
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    def __repr__(self):

        # Return a readable representation of the event object
        return f"<Event {self.title}>"