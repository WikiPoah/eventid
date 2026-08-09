from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.database.db import db
from app.models.attendance import Attendance
from app.models.event import Event
from app.models.event_category import EventCategory


def recommended_events(user_id, limit=6, candidate_limit=40):
    """Return bounded, deterministic recommendations for one authenticated user."""

    # Attendance history supplies only category and city affinity signals.
    preference_rows = db.session.execute(
        select(Event.city, EventCategory.category_id)
        .select_from(Attendance)
        .join(Event, Event.event_id == Attendance.event_id)
        .outerjoin(EventCategory, EventCategory.event_id == Event.event_id)
        .where(Attendance.user_id == user_id)
    ).all()
    preferred_cities = {row.city for row in preference_rows if row.city}
    preferred_categories = {
        row.category_id for row in preference_rows if row.category_id is not None
    }

    attendance_counts = (
        select(
            Attendance.event_id,
            func.count(Attendance.user_id).label("attendee_count"),
        )
        .group_by(Attendance.event_id)
        .subquery()
    )
    already_attending = (
        select(Attendance.user_id)
        .where(
            Attendance.user_id == user_id,
            Attendance.event_id == Event.event_id,
        )
        .exists()
    )

    # Fetch one bounded candidate set and eager-load categories without N+1 queries.
    candidate_rows = db.session.execute(
        select(
            Event,
            func.coalesce(attendance_counts.c.attendee_count, 0).label(
                "attendee_count"
            ),
        )
        .outerjoin(
            attendance_counts,
            attendance_counts.c.event_id == Event.event_id,
        )
        .where(
            Event.status == "Published",
            Event.privacy == "Public",
            Event.end_datetime >= datetime.now(),
            Event.organiser_id != user_id,
            ~already_attending,
            or_(
                Event.capacity.is_(None),
                func.coalesce(attendance_counts.c.attendee_count, 0) < Event.capacity,
            ),
        )
        .options(selectinload(Event.categories))
        .order_by(
            func.coalesce(attendance_counts.c.attendee_count, 0).desc(),
            Event.start_datetime,
            Event.event_id,
        )
        .limit(candidate_limit)
    ).all()

    def rank(row):
        event, attendee_count = row
        category_ids = {category.category_id for category in event.categories}
        # Category affinity leads, city follows, and popularity breaks cold starts.
        score = 100 * len(category_ids & preferred_categories)
        score += 25 if event.city in preferred_cities else 0
        score += min(int(attendee_count), 20)
        return (-score, event.start_datetime, event.event_id)

    return [row[0] for row in sorted(candidate_rows, key=rank)[:limit]]
