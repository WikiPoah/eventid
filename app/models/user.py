from datetime import datetime

from app.database.db import db


class User(db.Model):

    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)

    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)

    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    profile_picture_path = db.Column(db.String(255))

    bio = db.Column(db.Text)

    country = db.Column(db.String(100))
    city = db.Column(db.String(100))
    
    is_organiser = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):

        return f"<User {self.username}>"