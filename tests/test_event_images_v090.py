from io import BytesIO
from pathlib import Path

from app.database.db import db
from app.models.event import Event
from tests.conftest import login

PNG_IMAGE = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


def event_data(**overrides):
    values = {
        "title": "Image Event",
        "description": "Image test",
        "venue_name": "Image Hall",
        "address": "4 Image Street",
        "postcode": "10115",
        "city": "Berlin",
        "country": "Germany",
        "start_datetime": "2027-03-01T10:00",
        "end_datetime": "2027-03-01T12:00",
        "capacity": "10",
        "privacy": "Public",
        "status": "Published",
    }
    values.update(overrides)
    return values


def test_valid_image_upload_uses_safe_generated_filename(app, client, users):
    login(client, users[0])

    data = event_data(
        image=(
            BytesIO(PNG_IMAGE),
            "../../unsafe-name.png",
        )
    )

    response = client.post(
        "/events/create",
        data=data,
        content_type="multipart/form-data",
    )

    assert response.status_code == 302

    with app.app_context():
        event = Event.query.filter_by(
            title="Image Event"
        ).one()

        assert event.image_path.endswith(".png")
        assert "unsafe" not in event.image_path
        assert "/" not in event.image_path

        saved_path = (
            Path(
                app.config[
                    "EVENT_IMAGE_UPLOAD_FOLDER"
                ]
            )
            / event.image_path
        )

        assert (
            saved_path.read_bytes()
            == PNG_IMAGE
        )


def test_invalid_image_extension_and_signature_are_rejected(
    app,
    client,
    users,
):
    login(
        client,
        users[0],
    )

    response = client.post(
        "/events/create",
        data=event_data(
            image=(
                BytesIO(PNG_IMAGE),
                "image.gif",
            )
        ),
        content_type="multipart/form-data",
    )

    assert (
        b"Only JPEG, PNG and WebP images are allowed."
        in response.data
    )

    response = client.post(
        "/events/create",
        data=event_data(
            image=(
                BytesIO(b"not an image"),
                "image.png",
            )
        ),
        content_type="multipart/form-data",
    )

    assert (
        b"not a valid supported image"
        in response.data
    )

    with app.app_context():
        assert (
            Event.query.filter_by(
                title="Image Event"
            ).count()
            == 0
        )


def test_oversized_image_is_rejected(
    app,
    client,
    users,
):
    app.config[
        "EVENT_IMAGE_MAX_BYTES"
    ] = 16

    login(
        client,
        users[0],
    )

    response = client.post(
        "/events/create",
        data=event_data(
            image=(
                BytesIO(PNG_IMAGE),
                "large.png",
            )
        ),
        content_type="multipart/form-data",
    )

    assert (
        b"4 MB or smaller"
        in response.data
    )


def test_organiser_can_replace_image_and_old_file_is_removed(
    app,
    client,
    users,
    event_factory,
):
    upload_directory = Path(
        app.config[
            "EVENT_IMAGE_UPLOAD_FOLDER"
        ]
    )

    upload_directory.mkdir(
        parents=True
    )

    old_path = (
        upload_directory
        / "old.png"
    )

    old_path.write_bytes(
        PNG_IMAGE
    )

    event_id = event_factory(
        image_path="old.png"
    )

    login(
        client,
        users[0],
    )

    response = client.post(
        f"/events/{event_id}/edit",
        data=event_data(
            image=(
                BytesIO(PNG_IMAGE),
                "replacement.png",
            )
        ),
        content_type="multipart/form-data",
    )

    assert (
        response.status_code
        == 302
    )

    with app.app_context():
        new_name = db.session.get(
            Event,
            event_id,
        ).image_path

    assert (
        new_name
        != "old.png"
    )

    assert not old_path.exists()

    assert (
        upload_directory
        / new_name
    ).exists()


def test_unauthorised_user_cannot_replace_image(
    app,
    client,
    users,
    event_factory,
):
    event_id = event_factory()

    login(
        client,
        users[1],
    )

    response = client.post(
        f"/events/{event_id}/edit",
        data=event_data(
            image=(
                BytesIO(PNG_IMAGE),
                "replacement.png",
            )
        ),
        content_type="multipart/form-data",
    )

    assert (
        response.status_code
        == 403
    )

    with app.app_context():
        assert (
            db.session.get(
                Event,
                event_id,
            ).image_path
            is None
        )


def test_image_fallback_and_image_access_rules(
    app,
    client,
    users,
    event_factory,
):
    public_id = event_factory(
        image_path=None
    )

    event_factory(
        status="Draft",
        image_path="private.png",
    )

    upload_directory = Path(
        app.config[
            "EVENT_IMAGE_UPLOAD_FOLDER"
        ]
    )

    upload_directory.mkdir(
        parents=True
    )

    (
        upload_directory
        / "private.png"
    ).write_bytes(
        PNG_IMAGE
    )

    login(
        client,
        users[1],
    )

    assert (
        b"No event image available"
        in client.get(
            f"/events/{public_id}"
        ).data
    )

    assert (
        client.get(
            "/event-images/private.png"
        ).status_code
        == 403
    )

    login(
        client,
        users[0],
    )

    image_response = client.get(
        "/event-images/private.png"
    )

    assert (
        image_response.status_code
        == 200
    )

    assert (
        image_response.headers[
            "X-Content-Type-Options"
        ]
        == "nosniff"
    )

    assert (
        client.get(
            "/event-images/../private.png"
        ).status_code
        == 404
    )