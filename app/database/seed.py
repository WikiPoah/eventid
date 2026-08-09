from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from werkzeug.security import generate_password_hash

from app.database.db import db
from app.models.attendance import Attendance
from app.models.category import Category
from app.models.event import Event
from app.models.event_category import EventCategory
from app.models.user import User

# Define the default event categories available in the application
EVENT_CATEGORIES = [
    "Arts & Culture",
    "Community & Charity",
    "Education & STEM",
    "Food & Drink",
    "Music",
    "Networking",
    "Socialising",
    "Sports & Fitness",
    "Technology",
]


def seed_categories():

    # Insert each predefined category if it doesn't already exist
    for category_name in EVENT_CATEGORIES:

        existing_category = Category.query.filter_by(name=category_name).first()

        if existing_category is None:

            db.session.add(Category(name=category_name))

    # Save any newly added categories to the database
    db.session.commit()


DEMO_PASSWORD = "EventID-demo-2026"

DEMO_USERS = [
    {
        "username": "demo_organiser",
        "email": "demo-organiser@example.test",
        "first_name": "Maya",
        "last_name": "Morgan",
        "is_organiser": True,
    },
    {
        "username": "demo_attendee",
        "email": "demo-attendee@example.test",
        "first_name": "Alex",
        "last_name": "Rivera",
        "is_organiser": False,
    },
    {
        "username": "demo_jordan",
        "email": "demo-jordan@example.test",
        "first_name": "Jordan",
        "last_name": "Lee",
        "is_organiser": False,
    },
    {
        "username": "demo_samira",
        "email": "demo-samira@example.test",
        "first_name": "Samira",
        "last_name": "Khan",
        "is_organiser": False,
    },
    {
        "username": "demo_tomasz",
        "email": "demo-tomasz@example.test",
        "first_name": "Tomasz",
        "last_name": "Nowak",
        "is_organiser": False,
    },
]


def _demo_user(user_data):
    """Create or retrieve one clearly identified development account."""

    existing = db.session.scalar(
        select(User).where(
            or_(
                User.username == user_data["username"],
                User.email == user_data["email"],
            )
        )
    )
    if existing is not None:
        if (
            existing.username != user_data["username"]
            or existing.email != user_data["email"]
        ):
            raise RuntimeError(
                "A real account conflicts with a reserved demo username or email."
            )
        return existing, False

    user = User(
        first_name=user_data["first_name"],
        last_name=user_data["last_name"],
        username=user_data["username"],
        email=user_data["email"],
        password_hash=generate_password_hash(DEMO_PASSWORD),
        is_organiser=user_data["is_organiser"],
    )
    db.session.add(user)
    return user, True


def _demo_event(organiser, now, event_data, categories_by_name):
    """Create one deterministic demo event without modifying an existing one."""

    existing = db.session.scalar(
        select(Event).where(
            Event.organiser_id == organiser.user_id,
            Event.title == event_data["title"],
        )
    )
    if existing is not None:
        # Refresh only demo schedule fields so seeded timelines stay useful
        existing.start_datetime = now + event_data["start_offset"]
        existing.end_datetime = now + event_data["end_offset"]
        return existing, False

    event = Event(
        title=event_data["title"],
        description=event_data["description"],
        venue_name=event_data["venue_name"],
        address=event_data["address"],
        postcode=event_data["postcode"],
        city=event_data["city"],
        country=event_data["country"],
        location_notes=event_data.get("location_notes"),
        start_datetime=now + event_data["start_offset"],
        end_datetime=now + event_data["end_offset"],
        capacity=event_data["capacity"],
        privacy=event_data["privacy"],
        status=event_data["status"],
        organiser_id=organiser.user_id,
    )
    db.session.add(event)
    db.session.flush()
    for category_name in event_data["categories"]:
        db.session.add(
            EventCategory(
                event_id=event.event_id,
                category_id=categories_by_name[category_name].category_id,
            )
        )
    return event, True


def seed_demo_data():
    """Create safe, repeatable users, events, and attendance for development."""

    seed_categories()
    now = datetime.now(UTC).replace(
        tzinfo=None,
        hour=18,
        minute=0,
        second=0,
        microsecond=0,
    )
    categories_by_name = {
        category.name: category
        for category in Category.query.filter(Category.name.in_(EVENT_CATEGORIES)).all()
    }

    # Create clearly identified demo accounts without replacing real users
    users = {}
    users_created = 0
    for user_data in DEMO_USERS:
        user, created = _demo_user(user_data)
        users[user_data["username"]] = user
        users_created += created
    db.session.flush()

    # Generate dates relative to current UTC so demonstrations remain useful
    event_definitions = [
        {
            "title": "Bremen Technology Meetup",
            "description": "A practical evening of fictional product demos and developer conversations.",
            "venue_name": "Weser Innovation Hall",
            "address": "14 Demo Quay",
            "postcode": "28195",
            "city": "Bremen",
            "country": "Germany",
            "start_offset": timedelta(days=14),
            "end_offset": timedelta(days=14, hours=3),
            "capacity": 50,
            "privacy": "Public",
            "status": "Published",
            "categories": ["Technology", "Networking"],
        },
        {
            "title": "Hamburg Community Workshop",
            "description": "A hands-on planning session for fictional neighbourhood projects.",
            "venue_name": "Harbour Community Studio",
            "address": "8 Sample Lane",
            "postcode": "20095",
            "city": "Hamburg",
            "country": "Germany",
            "start_offset": timedelta(days=7),
            "end_offset": timedelta(days=7, hours=2),
            "capacity": 5,
            "privacy": "Public",
            "status": "Published",
            "categories": ["Community & Charity", "Education & STEM"],
        },
        {
            "title": "Berlin Indie Music Night",
            "description": "An intimate showcase featuring fictional independent artists.",
            "venue_name": "Demo Sound Room",
            "address": "22 Example Strasse",
            "postcode": "10115",
            "city": "Berlin",
            "country": "Germany",
            "start_offset": timedelta(days=21),
            "end_offset": timedelta(days=21, hours=4),
            "capacity": 3,
            "privacy": "Public",
            "status": "Published",
            "categories": ["Music", "Socialising"],
        },
        {
            "title": "London Open Data Forum",
            "description": "A fictional public forum about accessible civic information.",
            "venue_name": "Thames Demo Centre",
            "address": "5 Example Square",
            "postcode": "SW1A 1AA",
            "city": "London",
            "country": "United Kingdom",
            "start_offset": timedelta(days=35),
            "end_offset": timedelta(days=35, hours=3),
            "capacity": None,
            "privacy": "Public",
            "status": "Published",
            "categories": ["Technology", "Education & STEM"],
        },
        {
            "title": "Warsaw Design Exchange",
            "description": "A fictional exchange for local designers and creative teams.",
            "venue_name": "Vistula Design Lab",
            "address": "19 Sample Street",
            "postcode": "00-001",
            "city": "Warsaw",
            "country": "Poland",
            "start_offset": timedelta(days=10),
            "end_offset": timedelta(days=10, hours=3),
            "capacity": 25,
            "privacy": "Public",
            "status": "Published",
            "categories": ["Arts & Culture", "Networking"],
        },
        {
            "title": "Leipzig Organiser Planning Session",
            "description": "A private fictional planning session for the demo organiser.",
            "venue_name": "Private Meeting Room",
            "address": "3 Internal Way",
            "postcode": "04109",
            "city": "Leipzig",
            "country": "Germany",
            "start_offset": timedelta(days=5),
            "end_offset": timedelta(days=5, hours=2),
            "capacity": 8,
            "privacy": "Private",
            "status": "Published",
            "categories": ["Networking"],
        },
        {
            "title": "Dresden Future Food Fair",
            "description": "A draft concept for a fictional sustainable food fair.",
            "venue_name": "Elbe Exhibition Space",
            "address": "41 Preview Road",
            "postcode": "01067",
            "city": "Dresden",
            "country": "Germany",
            "start_offset": timedelta(days=28),
            "end_offset": timedelta(days=28, hours=5),
            "capacity": 100,
            "privacy": "Public",
            "status": "Draft",
            "categories": ["Food & Drink"],
        },
        {
            "title": "Cologne Riverside Run",
            "description": "A cancelled fictional community running event.",
            "venue_name": "Riverside Meeting Point",
            "address": "7 Cancelled Route",
            "postcode": "50667",
            "city": "Cologne",
            "country": "Germany",
            "start_offset": timedelta(days=3),
            "end_offset": timedelta(days=3, hours=2),
            "capacity": 40,
            "privacy": "Public",
            "status": "Cancelled",
            "categories": ["Sports & Fitness"],
        },
        {
            "title": "Bremen Makers Day Archive",
            "description": "A completed fictional makers event retained for dashboard history.",
            "venue_name": "Weser Workshop",
            "address": "10 Archive Quay",
            "postcode": "28195",
            "city": "Bremen",
            "country": "Germany",
            "start_offset": timedelta(days=-10),
            "end_offset": timedelta(days=-10, hours=3),
            "capacity": 30,
            "privacy": "Public",
            "status": "Published",
            "categories": ["Technology", "Education & STEM"],
        },
        {
            "title": "Hamburg Networking Breakfast Archive",
            "description": "A completed fictional professional breakfast event.",
            "venue_name": "Harbour Breakfast Room",
            "address": "16 Archive Street",
            "postcode": "20095",
            "city": "Hamburg",
            "country": "Germany",
            "start_offset": timedelta(days=-30),
            "end_offset": timedelta(days=-30, hours=2),
            "capacity": None,
            "privacy": "Public",
            "status": "Published",
            "categories": ["Networking"],
        },
    ]

    organiser = users["demo_organiser"]
    events = {}
    events_created = 0
    for event_data in event_definitions:
        event, created = _demo_event(organiser, now, event_data, categories_by_name)
        events[event_data["title"]] = event
        events_created += created

    # Add deterministic registrations for ordinary, nearly-full, and full cases
    attendance_plan = {
        "Bremen Technology Meetup": ["demo_attendee", "demo_jordan"],
        "Hamburg Community Workshop": [
            "demo_attendee",
            "demo_jordan",
            "demo_samira",
            "demo_tomasz",
        ],
        "Berlin Indie Music Night": [
            "demo_attendee",
            "demo_jordan",
            "demo_samira",
        ],
        "London Open Data Forum": ["demo_attendee"],
        "Warsaw Design Exchange": ["demo_attendee", "demo_tomasz"],
        "Cologne Riverside Run": ["demo_attendee"],
        "Bremen Makers Day Archive": ["demo_attendee", "demo_samira"],
    }
    attendances_created = 0
    for event_title, usernames in attendance_plan.items():
        event = events[event_title]
        for username in usernames:
            user = users[username]
            if db.session.get(Attendance, (user.user_id, event.event_id)) is None:
                db.session.add(
                    Attendance(
                        user_id=user.user_id,
                        event_id=event.event_id,
                    )
                )
                attendances_created += 1

    db.session.commit()
    return {
        "users_created": users_created,
        "events_created": events_created,
        "attendances_created": attendances_created,
    }
