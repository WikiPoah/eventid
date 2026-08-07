from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.db import db
from app.models.event import Event


def public_homepage_events(limit=12):
    """Return bounded public discovery groups for the landing page."""

    now = datetime.now()
    week_end = now + timedelta(days=7)
    public_upcoming = (
        Event.status == "Published",
        Event.privacy == "Public",
        Event.end_datetime >= now,
    )

    this_week = db.session.scalars(
        select(Event)
        .where(*public_upcoming, Event.start_datetime <= week_end)
        .options(selectinload(Event.categories))
        .order_by(Event.start_datetime, Event.event_id)
        .limit(limit)
    ).all()
    more_upcoming = db.session.scalars(
        select(Event)
        .where(*public_upcoming, Event.start_datetime > week_end)
        .options(selectinload(Event.categories))
        .order_by(Event.start_datetime, Event.event_id)
        .limit(limit)
    ).all()
    return this_week, more_upcoming
