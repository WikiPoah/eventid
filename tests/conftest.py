import os
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("SECRET_KEY", "test-only-secret-key")

from app.database.db import db
from app.models.event import Event
from app.models.user import User
from app.rate_limit import limiter
from main import create_app


@pytest.fixture
def app(tmp_path):
    database_path = (tmp_path / "eventid-test.db").as_posix()
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-only-secret-key",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "WTF_CSRF_ENABLED": False,
            "LOGIN_RATE_LIMIT": "3 per minute",
            "EVENT_IMAGE_UPLOAD_FOLDER": str(tmp_path / "event-images"),
        }
    )

    with application.app_context():
        limiter.storage.reset()
        db.create_all()
        yield application
        limiter.storage.reset()
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def users(app):
    with app.app_context():
        organiser = User(
            first_name="Olivia",
            last_name="Organiser",
            username="organiser",
            email="organiser@example.test",
            password_hash="unused",
        )
        attendee = User(
            first_name="Alice",
            last_name="Attendee",
            username="attendee",
            email="attendee@example.test",
            password_hash="unused",
        )
        other = User(
            first_name="Oscar",
            last_name="Other",
            username="other",
            email="other@example.test",
            password_hash="unused",
        )
        db.session.add_all([organiser, attendee, other])
        db.session.commit()
        return organiser.user_id, attendee.user_id, other.user_id


@pytest.fixture
def event_factory(app, users):
    organiser_id = users[0]

    def create_event(**overrides):
        values = {
            "title": "Public Event",
            "description": "An event used by the test suite.",
            "venue_name": "Test Hall",
            "address": "1 Test Street",
            "postcode": "10115",
            "city": "Berlin",
            "country": "Germany",
            "start_datetime": datetime.now() + timedelta(days=1),
            "end_datetime": datetime.now() + timedelta(days=1, hours=2),
            "status": "Published",
            "privacy": "Public",
            "capacity": 10,
            "organiser_id": organiser_id,
        }
        values.update(overrides)
        with app.app_context():
            event = Event(**values)
            db.session.add(event)
            db.session.commit()
            return event.event_id

    return create_event


def login(client, user_id):
    with client.session_transaction() as session:
        session["user_id"] = user_id
