from datetime import UTC, datetime

from app.database.db import db


class UserSession(db.Model):
    __tablename__ = "user_sessions"

    session_id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    user_agent = db.Column(db.String(255), nullable=False)
    ip_address = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), nullable=False)
    last_seen_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), nullable=False)
    revoked_at = db.Column(db.DateTime)

    user = db.relationship("User", back_populates="sessions")


class SecurityEvent(db.Model):
    __tablename__ = "security_events"

    security_event_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    event_type = db.Column(db.String(40), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    ip_address = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), nullable=False)

    user = db.relationship("User", back_populates="security_events")
