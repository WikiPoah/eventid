from app.database.db import db
from app.models.category import Category
from app.models.event import Event
from tests.conftest import login


def test_event_creation_preserves_categories_and_privacy(app, client, users):
    with app.app_context():
        category = Category(name="Technology")
        db.session.add(category)
        db.session.commit()
        category_id = category.category_id

    login(client, users[0])
    response = client.post(
        "/events/create",
        data={
            "title": "Created Event",
            "description": "Created through the form.",
            "venue_name": "Creation Hall",
            "address": "2 Test Street",
            "city": "Berlin",
            "country": "Germany",
            "start_datetime": "2027-01-01T10:00",
            "end_datetime": "2027-01-01T12:00",
            "capacity": "25",
            "privacy": "Private",
            "categories": str(category_id),
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/manage-events")

    with app.app_context():
        event = Event.query.filter_by(title="Created Event").one()
        assert event.privacy == "Private"
        assert event.capacity == 25
        assert [category.name for category in event.categories] == ["Technology"]
