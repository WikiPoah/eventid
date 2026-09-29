from app.database.db import db
from app.models.attendance import Attendance
from app.models.category import Category
from app.models.event import Event
from app.models.event_category import EventCategory
from tests.conftest import login


def test_organiser_can_preview_event_as_attendee(client, users, event_factory):
    event_id = event_factory(status="Draft", title="Preview Draft")
    login(client, users[0])

    response = client.get(f"/events/{event_id}/preview", follow_redirects=True)

    assert response.status_code == 200
    assert b"Attendee preview" in response.data
    assert b"Registration area preview" in response.data
    assert b"Exit preview" in response.data
    assert b"Attendance Requests" not in response.data
    assert b">Edit Event<" not in response.data


def test_preview_is_owner_only(client, users, event_factory):
    event_id = event_factory()
    login(client, users[1])

    assert client.get(f"/events/{event_id}/preview").status_code == 403


def test_duplicate_event_creates_clean_draft(app, client, users, event_factory):
    event_id = event_factory(
        title="Original Event",
        privacy="Private",
        invite_token="original-private-token",
        image_path="original-image.jpg",
    )
    with app.app_context():
        category = Category(name="Duplicate Test")
        db.session.add(category)
        db.session.flush()
        db.session.add_all(
            [
                EventCategory(event_id=event_id, category_id=category.category_id),
                Attendance(user_id=users[1], event_id=event_id, status="Going"),
            ]
        )
        db.session.commit()

    login(client, users[0])
    response = client.post(f"/events/{event_id}/duplicate")

    assert response.status_code == 302
    with app.app_context():
        duplicate = Event.query.filter_by(title="Copy of Original Event").one()
        assert duplicate.status == "Draft"
        assert duplicate.requests_open is False
        assert duplicate.image_path is None
        assert duplicate.invite_token != "original-private-token"
        assert [category.name for category in duplicate.categories] == [
            "Duplicate Test"
        ]
        assert duplicate.attendees == []


def test_duplicate_event_is_owner_only(client, users, event_factory):
    event_id = event_factory()
    login(client, users[1])

    assert client.post(f"/events/{event_id}/duplicate").status_code == 403
