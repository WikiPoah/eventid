from datetime import datetime, UTC

from app.database.db import db


# Store account details and profile information for each user
class User(db.Model):

    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)

    # Store the user's personal information
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)

    # Store the user's login credentials
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    # Store the path to the user's profile picture
    profile_picture_path = db.Column(db.String(255))

    # Allow users to add a short biography to their profile
    bio = db.Column(db.Text)

    # Store the user's location information
    country = db.Column(db.String(100))
    city = db.Column(db.String(100))

    # Track organiser permissions and account creation date
    is_organiser = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Link each user to the events they organise and attend
    events = db.relationship(
        "Event",
        back_populates="organiser"
    )

    attendances = db.relationship(
        "Attendance",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # Provide read-only event access while retaining attendance records
    attending_events = db.relationship(
        "Event",
        secondary="attendance",
        viewonly=True
    )

    def __repr__(self):

        # Return a readable representation of the user object
        return f"<User {self.username}>"
