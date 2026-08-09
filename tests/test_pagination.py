from datetime import datetime, timedelta

from app.database.db import db
from app.models.category import Category
from app.models.event_category import EventCategory
from tests.conftest import login


def test_browse_events_paginates_in_start_date_order(app, client, users, event_factory):
    for number in range(12):
        event_factory(
            title=f"Paginated Event {number:02d}",
            start_datetime=datetime.now() + timedelta(days=number + 1),
        )

    login(client, users[1])
    first_page = client.get("/events")
    second_page = client.get("/events?page=2")

    assert first_page.status_code == 200
    assert b"Paginated Event 00" in first_page.data
    assert b"Paginated Event 10" not in first_page.data
    assert b"Paginated Event 10" in second_page.data
    assert b"Previous" in second_page.data


def test_pagination_links_preserve_active_filters(app, client, users, event_factory):
    with app.app_context():
        category = Category(name="Pagination Category")
        db.session.add(category)
        db.session.commit()
        category_id = category.category_id

    for number in range(11):
        event_id = event_factory(
            title=f"Filtered Event {number:02d}",
            city="Hamburg",
        )
        with app.app_context():
            db.session.add(EventCategory(event_id=event_id, category_id=category_id))
            db.session.commit()

    event_factory(title="Filtered Event Elsewhere", city="Berlin")
    event_factory(title="Different Title", city="Hamburg")

    login(client, users[1])
    response = client.get(
        f"/events?search=Filtered&category={category_id}&city=Hamburg"
    )

    assert response.status_code == 200
    assert b"Filtered Event Elsewhere" not in response.data
    assert b"Different Title" not in response.data
    assert b"search=Filtered" in response.data
    assert f"category={category_id}".encode() in response.data
    assert b"city=Hamburg" in response.data


def test_invalid_or_empty_page_returns_not_found(client, users):
    login(client, users[1])
    assert client.get("/events?page=0").status_code == 404
    assert client.get("/events?page=999").status_code == 404
