from datetime import datetime

from app.database.db import db


# Store the relationship between users and the events they attend
class Attendance(db.Model):

    __tablename__ = "attendance"

    # Link each attendance record to a user and an event
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id"),
        primary_key=True
    )

    event_id = db.Column(
        db.Integer,
        db.ForeignKey("events.event_id"),
        primary_key=True
    )

    # Record when the user registered and their attendance status
    registered_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="Going"
    )

    # Allow navigation between attendance records, users and events
    user = db.relationship(
        "User",
        back_populates="attendances"
    )

    event = db.relationship(
        "Event",
        back_populates="attendees"
    )

    def __repr__(self):

        # Return a readable representation of the attendance record
        return f"<Attendance User {self.user_id} Event {self.event_id}>"