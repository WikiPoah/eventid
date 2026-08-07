import re
from datetime import datetime, timedelta

from tests.conftest import login


def test_anonymous_home_never_calculates_or_renders_recommendations(
    client, monkeypatch
):
    def unexpected_recommendation_call(*_args, **_kwargs):
        raise AssertionError("anonymous request calculated recommendations")

    monkeypatch.setattr("main.recommended_events", unexpected_recommendation_call)
    response = client.get("/")

    assert response.status_code == 200
    assert b"Events We Think You" not in response.data
    assert b'id="recommendations-title"' not in response.data
    assert b'id="recommendations-viewport"' not in response.data


def test_public_carousels_exclude_inaccessible_events(client, event_factory):
    now = datetime.now()
    event_factory(
        title="This Week Public",
        start_datetime=now + timedelta(days=2),
        end_datetime=now + timedelta(days=2, hours=2),
    )
    event_factory(
        title="Later Public",
        start_datetime=now + timedelta(days=10),
        end_datetime=now + timedelta(days=10, hours=2),
    )
    event_factory(title="Homepage Private", privacy="Private")
    event_factory(title="Homepage Draft", status="Draft")
    event_factory(title="Homepage Cancelled", status="Cancelled")
    event_factory(
        title="Homepage Expired",
        start_datetime=now - timedelta(days=2),
        end_datetime=now - timedelta(days=1),
    )

    response = client.get("/")
    assert b"Upcoming This Week" in response.data
    assert b"More Upcoming Events" in response.data
    assert b"This Week Public" in response.data
    assert b"Later Public" in response.data
    for excluded in (
        b"Homepage Private",
        b"Homepage Draft",
        b"Homepage Cancelled",
        b"Homepage Expired",
    ):
        assert excluded not in response.data


def test_each_sliding_carousel_has_unique_controls(client, event_factory):
    now = datetime.now()
    for number in range(2):
        event_factory(
            title=f"Week Slider {number}",
            start_datetime=now + timedelta(days=number + 1),
            end_datetime=now + timedelta(days=number + 1, hours=2),
        )
        event_factory(
            title=f"Later Slider {number}",
            start_datetime=now + timedelta(days=number + 9),
            end_datetime=now + timedelta(days=number + 9, hours=2),
        )

    html = client.get("/").get_data(as_text=True)
    viewport_ids = re.findall(r'id="([^"]+-viewport)"', html)
    controlled_ids = re.findall(r'aria-controls="([^"]+-viewport)"', html)

    assert viewport_ids == ["upcoming-week-viewport", "more-upcoming-viewport"]
    assert len(viewport_ids) == len(set(viewport_ids))
    assert controlled_ids.count("upcoming-week-viewport") == 2
    assert controlled_ids.count("more-upcoming-viewport") == 2
    assert html.count('aria-label="Previous events"') == 2
    assert html.count('aria-label="Next events"') == 2


def test_single_card_carousel_omits_controls(client, event_factory):
    now = datetime.now()
    event_factory(
        start_datetime=now + timedelta(days=2),
        end_datetime=now + timedelta(days=2, hours=2),
    )
    html = client.get("/").get_data(as_text=True)

    assert html.count("data-carousel") >= 2
    assert "data-carousel-controls" not in html


def test_authenticated_recommendation_carousel_is_independent(
    client, users, event_factory
):
    now = datetime.now()
    for number in range(2):
        event_factory(
            title=f"Recommendation Candidate {number}",
            start_datetime=now + timedelta(days=number + 9),
            end_datetime=now + timedelta(days=number + 9, hours=2),
        )

    login(client, users[2])
    html = client.get("/").get_data(as_text=True)
    viewport_ids = re.findall(r'id="([^"]+-viewport)"', html)

    assert "recommendations-viewport" in viewport_ids
    assert len(viewport_ids) == len(set(viewport_ids))
    assert 'aria-controls="recommendations-viewport"' in html
    assert "Events We Think You’ll Like" in html


def test_carousel_static_contract_supports_independent_responsive_motion(client):
    script = client.get("/static/js/script.js").get_data(as_text=True)
    styles = client.get("/static/css/style.css").get_data(as_text=True)

    assert 'querySelectorAll("[data-carousel]")' in script
    assert 'carousel.querySelector("[data-carousel-viewport]")' in script
    assert "getBoundingClientRect().width" in script
    assert "columnGap" in script
    assert "scrollBy" in script
    assert "ResizeObserver" in script
    assert 'querySelectorAll("img")' in script
    assert "document.fonts.ready" in script
    assert "prefers-reduced-motion: reduce" in styles
    assert "flex-flow: row nowrap" in styles
    assert "scroll-snap-type: x mandatory" in styles
