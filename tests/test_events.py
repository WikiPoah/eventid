from sqlalchemy.exc import SQLAlchemyError

from app.database.db import db
from app.models.attendance import Attendance
from app.models.category import Category
from app.models.event import Event
from app.models.event_category import EventCategory
from tests.conftest import login


def edit_data(**overrides):
    values = {
        "title": "Updated Event",
        "description": "Updated description",
        "venue_name": "Updated Hall",
        "address": "9 Updated Street",
        "postcode": "20095",
        "city": "Hamburg",
        "country": "Germany",
        "location_notes": "Use the side entrance",
        "latitude": "53.55",
        "longitude": "10.00",
        "start_datetime": "2027-02-01T10:00",
        "end_datetime": "2027-02-01T12:00",
        "capacity": "20",
        "privacy": "Public",
        "status": "Published",
    }
    values.update(overrides)
    return values


def test_organiser_can_edit_event_and_replace_categories(
    app, client, users, event_factory
):
    event_id = event_factory()

    with app.app_context():
        old = Category(name="Old Category")
        new = Category(name="New Category")

        db.session.add_all([old, new])
        db.session.flush()

        db.session.add(
            EventCategory(
                event_id=event_id,
                category_id=old.category_id,
            )
        )

        db.session.commit()

        new_id = new.category_id

    login(client, users[0])

    response = client.post(
        f"/events/{event_id}/edit",
        data=edit_data(
            categories=str(new_id)
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Event updated successfully." in response.data

    with app.app_context():
        event = db.session.get(
            Event,
            event_id,
        )

        assert event.title == "Updated Event"
        assert event.status == "Published"

        assert [
            category.name
            for category in event.categories
        ] == ["New Category"]


def test_edit_is_owner_only_and_missing_event_is_not_found(
    client,
    users,
    event_factory,
):
    event_id = event_factory()

    login(
        client,
        users[1],
    )

    assert (
        client.get(
            f"/events/{event_id}/edit"
        ).status_code
        == 403
    )

    login(
        client,
        users[0],
    )

    assert (
        client.get(
            "/events/999999/edit"
        ).status_code
        == 404
    )


def test_edit_rejects_invalid_dates_and_categories(
    app,
    client,
    users,
    event_factory,
):
    event_id = event_factory(
        title="Original"
    )

    login(
        client,
        users[0],
    )

    response = client.post(
        f"/events/{event_id}/edit",
        data=edit_data(
            start_datetime="2027-02-01T12:00",
            end_datetime="2027-02-01T10:00",
        ),
    )

    assert b"must be after the start" in response.data

    response = client.post(
        f"/events/{event_id}/edit",
        data=edit_data(
            categories="999999"
        ),
    )

    assert b"selected categories are invalid" in response.data

    with app.app_context():
        assert (
            db.session.get(
                Event,
                event_id,
            ).title
            == "Original"
        )


def test_capacity_cannot_be_reduced_below_attendance(
    app,
    client,
    users,
    event_factory,
):
    event_id = event_factory(
        capacity=10
    )

    with app.app_context():
        db.session.add_all(
            [
                Attendance(
                    user_id=users[1],
                    event_id=event_id,
                ),
                Attendance(
                    user_id=users[2],
                    event_id=event_id,
                ),
            ]
        )

        db.session.commit()

    login(
        client,
        users[0],
    )

    response = client.post(
        f"/events/{event_id}/edit",
        data=edit_data(
            capacity="1"
        ),
    )

    assert (
        b"Capacity cannot be lower than the 2 existing attendees"
        in response.data
    )

    with app.app_context():
        assert (
            db.session.get(
                Event,
                event_id,
            ).capacity
            == 10
        )


def test_edit_database_failure_rolls_back(
    app,
    client,
    users,
    event_factory,
    monkeypatch,
):
    event_id = event_factory(
        title="Before Failure"
    )

    login(
        client,
        users[0],
    )

    def fail_commit():
        raise SQLAlchemyError(
            "forced failure"
        )

    monkeypatch.setattr(
        db.session,
        "commit",
        fail_commit,
    )

    response = client.post(
        f"/events/{event_id}/edit",
        data=edit_data(),
    )

    assert response.status_code == 200
    assert b"could not be updated" in response.data

    with app.app_context():
        assert (
            db.session.get(
                Event,
                event_id,
            ).title
            == "Before Failure"
        )


def test_delete_is_owner_only_post_only_and_cascades(
    app,
    users,
    event_factory,
):
    event_id = event_factory()

    with app.app_context():
        category = Category(
            name="Delete Category"
        )

        db.session.add(
            category
        )
        db.session.flush()

        db.session.add_all(
            [
                Attendance(
                    user_id=users[1],
                    event_id=event_id,
                ),
                EventCategory(
                    event_id=event_id,
                    category_id=category.category_id,
                ),
            ]
        )

        db.session.commit()

    other_client = app.test_client()

    login(
        other_client,
        users[1],
    )

    assert (
        other_client.post(
            f"/events/{event_id}/delete"
        ).status_code
        == 403
    )

    owner_client = app.test_client()

    login(
        owner_client,
        users[0],
    )

    assert (
        owner_client.get(
            f"/events/{event_id}/delete"
        ).status_code
        == 405
    )

    response = owner_client.post(
        f"/events/{event_id}/delete",
        follow_redirects=True,
    )

    assert b"was deleted" in response.data

    with app.app_context():
        assert (
            db.session.get(
                Event,
                event_id,
            )
            is None
        )

        assert (
            Attendance.query.filter_by(
                event_id=event_id
            ).count()
            == 0
        )

        assert (
            EventCategory.query.filter_by(
                event_id=event_id
            ).count()
            == 0
        )


def test_delete_missing_event_and_csrf_requirement(
    app,
    client,
    users,
    event_factory,
):
    login(
        client,
        users[0],
    )

    assert (
        client.post(
            "/events/999999/delete"
        ).status_code
        == 404
    )

    event_id = event_factory()

    app.config[
        "WTF_CSRF_ENABLED"
    ] = True

    try:
        assert (
            client.post(
                f"/events/{event_id}/delete"
            ).status_code
            == 400
        )

    finally:
        app.config[
            "WTF_CSRF_ENABLED"
        ] = False


def test_status_change_is_owner_only(
    client,
    users,
    event_factory,
):
    event_id = event_factory()

    login(
        client,
        users[1],
    )

    assert (
        client.post(
            f"/events/{event_id}/status",
            data={
                "status": "Cancelled"
            },
        ).status_code
        == 403
    )

    login(
        client,
        users[0],
    )

    response = client.post(
        f"/events/{event_id}/status",
        data={
            "status": "Cancelled"
        },
        follow_redirects=True,
    )

    assert (
        b"status changed to Cancelled"
        in response.data
    )