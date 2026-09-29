import re
from datetime import datetime, timedelta

from sqlalchemy import event as sqlalchemy_event
from werkzeug.security import generate_password_hash

from app.database.db import db
from app.models.attendance import Attendance
from app.models.category import Category
from app.models.event_category import EventCategory
from app.models.user import User
from app.recommendations import recommended_events
from tests.conftest import login


def add_category(app, name):
    with app.app_context():
        category = Category(name=name)
        db.session.add(category)
        db.session.commit()
        return category.category_id


def categorise(app, event_id, category_id):
    with app.app_context():
        db.session.add(
            EventCategory(
                event_id=event_id,
                category_id=category_id,
            )
        )
        db.session.commit()


def attend(app, user_id, event_id):
    with app.app_context():
        db.session.add(
            Attendance(
                user_id=user_id,
                event_id=event_id,
            )
        )
        db.session.commit()


def test_anonymous_public_discovery_filters_pagination_and_details(
    app,
    client,
    event_factory,
):
    category_id = add_category(
        app,
        "Public Discovery",
    )

    first_id = None

    for number in range(11):
        event_id = event_factory(
            title=f"Public Match {number:02d}",
            city="Hamburg",
            start_datetime=datetime.now() + timedelta(days=number + 1),
            end_datetime=datetime.now()
            + timedelta(
                days=number + 1,
                hours=2,
            ),
        )

        first_id = first_id or event_id

        categorise(
            app,
            event_id,
            category_id,
        )

    assert client.get("/").status_code == 200

    response = client.get(f"/events?search=Public&category={category_id}&city=Hamburg")

    assert response.status_code == 200
    assert b"Public Match 00" in response.data
    assert b"page=2" in response.data

    assert client.get("/events?page=2").status_code == 200

    assert client.get(f"/events/{first_id}").status_code == 200


def test_anonymous_visibility_excludes_non_public_events(
    client,
    event_factory,
):
    public_id = event_factory(title="Visible Public")

    private_id = event_factory(
        title="Hidden Private",
        privacy="Private",
    )

    draft_id = event_factory(
        title="Hidden Draft",
        status="Draft",
    )

    cancelled_id = event_factory(
        title="Hidden Cancelled",
        status="Cancelled",
    )

    browse = client.get("/events")

    assert b"Visible Public" in browse.data
    assert b"Hidden Private" not in browse.data
    assert b"Hidden Draft" not in browse.data
    assert b"Hidden Cancelled" not in browse.data

    assert client.get(f"/events/{public_id}").status_code == 200

    assert client.get(f"/events/{private_id}").status_code == 403

    assert client.get(f"/events/{draft_id}").status_code == 403

    assert client.get(f"/events/{cancelled_id}").status_code == 403


def test_browse_search_matches_title_fragments_and_small_typos(client, event_factory):
    event_factory(title="Berlin Indie Music Night")
    event_factory(title="Community Gardening Workshop")

    partial_response = client.get("/events?search=music")
    typo_response = client.get("/events?search=muisc+nigt")

    assert b"Berlin Indie Music Night" in partial_response.data
    assert b"Berlin Indie Music Night" in typo_response.data
    assert b"Community Gardening Workshop" not in typo_response.data


def test_browse_search_explains_supported_input(client):
    response = client.get("/events")

    assert b"Title, description, venue or category..." in response.data


def test_browse_searches_description_venue_city_and_category(
    app, client, event_factory
):
    category_id = add_category(app, "Creative Coding")
    event_id = event_factory(
        title="A Different Name",
        description="Learn experimental projection techniques.",
        venue_name="Riverside Studio",
        city="Potsdam",
    )
    categorise(app, event_id, category_id)

    for search_term in ["projection", "Riverside", "Potsdam", "Creative Coding"]:
        response = client.get("/events", query_string={"search": search_term})
        assert b"A Different Name" in response.data

    typo_response = client.get("/events?search=projetcion")
    assert b"A Different Name" in typo_response.data


def test_browse_shows_result_count_and_removable_active_filters(
    app, client, event_factory
):
    category_id = add_category(app, "Filter Summary")
    event_id = event_factory(title="Summary Match", city="Hamburg")
    categorise(app, event_id, category_id)

    response = client.get(f"/events?search=Summary&category={category_id}&city=Hamburg")

    assert b"1</strong> event found" in response.data
    assert b"Search:" in response.data
    assert b"#Filter Summary" in response.data
    assert b"Hamburg" in response.data
    assert b"Clear all" in response.data


def test_browse_can_match_any_of_multiple_categories(app, client, event_factory):
    music_id = add_category(app, "Music Filter")
    gaming_id = add_category(app, "Gaming Filter")
    other_id = add_category(app, "Other Filter")
    music_event = event_factory(title="Music Choice")
    gaming_event = event_factory(title="Gaming Choice")
    other_event = event_factory(title="Other Choice")
    categorise(app, music_event, music_id)
    categorise(app, gaming_event, gaming_id)
    categorise(app, other_event, other_id)

    response = client.get(f"/events?category={music_id}&category={gaming_id}")

    assert b"Music Choice" in response.data
    assert b"Gaming Choice" in response.data
    assert b"Other Choice" not in response.data
    assert response.data.count(b'name="category"') >= 3


def test_anonymous_navigation_and_attend_return_flow(
    app,
    client,
    users,
    event_factory,
):
    event_id = event_factory()

    details = client.get(f"/events/{event_id}")

    assert b"Browse Events" in details.data
    assert b"My Events" in details.data
    assert b"Manage Events" in details.data
    assert b"Create Event" in details.data

    assert b"Log in" in details.data
    assert b"Sign up" in details.data

    assert b"Log In to Attend" in details.data

    response = client.post(f"/events/{event_id}/attend")

    assert response.status_code == 302

    assert response.headers["Location"].endswith(f"/login?next=/events/{event_id}")

    login_page = client.get(
        response.headers["Location"],
        follow_redirects=True,
    )

    assert (
        b"Please log in or create an account to attend this event." in login_page.data
    )

    with app.app_context():
        user = db.session.get(
            User,
            users[1],
        )

        user.password_hash = generate_password_hash("safe-test-password")

        db.session.commit()

    login_response = client.post(
        "/login",
        data={
            "username": "attendee",
            "password": "safe-test-password",
            "next": f"/events/{event_id}",
        },
    )

    assert login_response.headers["Location"].endswith(f"/events/{event_id}")


def test_external_next_url_is_rejected(
    app,
    client,
    users,
):
    with app.app_context():
        user = db.session.get(
            User,
            users[1],
        )

        user.password_hash = generate_password_hash("safe-test-password")

        db.session.commit()

    response = client.post(
        "/login",
        data={
            "username": "attendee",
            "password": "safe-test-password",
            "next": "https://attacker.example/steal",
        },
    )

    assert response.status_code == 302

    assert response.headers["Location"].endswith("/")

    assert "attacker.example" not in response.headers["Location"]


def test_personal_pages_remain_protected(
    client,
):
    expected = {
        "/my-events": "Please log in to view your events.",
        "/manage-events": "Please log in to manage events.",
        "/events/create": "Please log in to create an event.",
    }

    for path, message in expected.items():
        response = client.get(path)

        assert response.status_code == 302

        assert response.headers["Location"].startswith("/login?next=")

        page = client.get(
            response.headers["Location"],
            follow_redirects=True,
        )

        assert message.encode() in page.data


def test_recommendations_rank_affinity_and_apply_all_exclusions(
    app,
    users,
    event_factory,
):
    music_id = add_category(
        app,
        "Recommendation Music",
    )

    history_id = event_factory(city="Bremen")

    categorise(
        app,
        history_id,
        music_id,
    )

    attend(
        app,
        users[1],
        history_id,
    )

    category_match = event_factory(
        title="Category Match",
        city="Berlin",
    )

    categorise(
        app,
        category_match,
        music_id,
    )

    event_factory(
        title="City Match",
        city="Bremen",
    )

    attended_id = event_factory(title="Already Attended")

    attend(
        app,
        users[1],
        attended_id,
    )

    event_factory(
        title="Owned Event",
        organiser_id=users[1],
    )

    event_factory(
        title="Private Candidate",
        privacy="Private",
    )

    event_factory(
        title="Draft Candidate",
        status="Draft",
    )

    event_factory(
        title="Cancelled Candidate",
        status="Cancelled",
    )

    event_factory(
        title="Past Candidate",
        start_datetime=datetime.now() - timedelta(days=2),
        end_datetime=datetime.now() - timedelta(days=1),
    )

    full_id = event_factory(
        title="Full Candidate",
        capacity=1,
    )

    attend(
        app,
        users[2],
        full_id,
    )

    with app.app_context():
        recommendations = recommended_events(users[1])

        titles = [event.title for event in recommendations]

    assert titles.index("Category Match") < titles.index("City Match")

    for excluded in (
        "Already Attended",
        "Owned Event",
        "Private Candidate",
        "Draft Candidate",
        "Cancelled Candidate",
        "Past Candidate",
        "Full Candidate",
    ):
        assert excluded not in titles


def test_recommendations_are_bounded_private_and_have_cold_start(
    app,
    client,
    users,
    event_factory,
):
    for number in range(9):
        event_factory(title=f"Cold Start {number}")

    assert b"Events We Think You" not in client.get("/").data

    login(
        client,
        users[2],
    )

    response = client.get("/")

    assert b"Events We Think You" in response.data

    assert b"Browse all events" in response.data

    recommendation_section = re.search(
        rb'<section[^>]+aria-labelledby="recommendations-title"(.*?)</section>',
        response.data,
        re.DOTALL,
    ).group(1)

    assert recommendation_section.count(b'class="event-card stagger-item') == 6


def test_recommendations_use_at_most_three_select_queries(
    app,
    users,
    event_factory,
):
    for number in range(4):
        event_factory(title=f"Efficient Candidate {number}")

    selects = 0

    def count_selects(
        _connection,
        _cursor,
        statement,
        *_args,
    ):
        nonlocal selects

        if statement.lstrip().upper().startswith("SELECT"):
            selects += 1

    with app.app_context():
        sqlalchemy_event.listen(
            db.engine,
            "before_cursor_execute",
            count_selects,
        )

        try:
            recommendations = recommended_events(users[1])

        finally:
            sqlalchemy_event.remove(
                db.engine,
                "before_cursor_execute",
                count_selects,
            )

    assert recommendations
    assert selects <= 3
