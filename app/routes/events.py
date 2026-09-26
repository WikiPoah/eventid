import csv
import re
import secrets
from calendar import Calendar, month_name
from datetime import UTC, date, datetime, timedelta
from difflib import SequenceMatcher
from io import BytesIO, StringIO
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import qrcode
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.database.db import db
from app.decorators import login_required
from app.event_images import (
    delete_event_image,
    save_event_image,
    validate_event_image,
)
from app.forms.event_forms import EventForm
from app.models.attendance import Attendance
from app.models.category import Category
from app.models.event import Event
from app.models.event_category import EventCategory
from app.models.favourite import Favourite
from app.rate_limit import limiter

events = Blueprint("events", __name__)

NEARLY_FULL_THRESHOLD = 0.8
EVENT_STATUSES = {"Draft", "Published", "Cancelled"}


def _event_matches_search(event, search):
    """Search public event details while tolerating modest word-level typos."""

    searchable_text = " ".join(
        [
            event.title,
            event.description,
            event.venue_name,
            event.city,
            *(category.name for category in event.categories),
        ]
    ).casefold()
    search_text = search.casefold()
    if search_text in searchable_text:
        return True

    searchable_words = re.findall(r"[\w]+", searchable_text)
    search_words = re.findall(r"[\w]+", search_text)
    return bool(search_words) and all(
        any(
            len(search_word) >= 4
            and SequenceMatcher(None, search_word, searchable_word).ratio() >= 0.75
            for searchable_word in searchable_words
        )
        for search_word in search_words
    )


def _safe_csv_value(value):
    """Prevent attendee-controlled text from becoming a spreadsheet formula."""

    text_value = str(value)
    if text_value.startswith(("=", "+", "-", "@")):
        return f"'{text_value}"
    return text_value


def _ics_escape(value):
    """Escape user-controlled text for an iCalendar property value."""

    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def _event_timezone():
    """Return the configured event timezone with a safe UTC fallback."""
    try:
        return ZoneInfo(current_app.config["EVENT_TIMEZONE"])
    except ZoneInfoNotFoundError:
        current_app.logger.error("Unknown EVENT_TIMEZONE; falling back to UTC")
        return UTC


def _ics_utc(local_datetime):
    """Convert a naive event datetime from the configured timezone to UTC."""

    return (
        local_datetime.replace(tzinfo=_event_timezone())
        .astimezone(UTC)
        .strftime("%Y%m%dT%H%M%SZ")
    )


def _calendar_iso(local_datetime):
    """Return an unambiguous ISO timestamp for web-calendar providers."""

    return local_datetime.replace(tzinfo=_event_timezone()).isoformat()


def _event_calendar_location(event):
    """Return a readable event address for calendar integrations."""

    return ", ".join(
        part
        for part in [
            event.venue_name,
            event.address,
            event.postcode,
            event.city,
            event.country,
        ]
        if part
    )


def _event_map_destination(event):
    """Prefer exact event coordinates and fall back to the full address."""

    if event.latitude is not None and event.longitude is not None:
        return f"{event.latitude:.6f},{event.longitude:.6f}"
    return _event_calendar_location(event)


def _owned_event_or_404(event_id, *, lock=False):
    """Return an event owned by the current user or reject access."""

    event = _locked_event(event_id) if lock else db.get_or_404(Event, event_id)
    if event is None:
        abort(404)

    # Enforce organiser ownership independently of displayed actions
    if event.organiser_id != g.user.user_id:
        abort(403)

    return event


def _category_ids(categories):
    """Validate submitted category identifiers against database records."""

    try:
        selected_ids = {
            int(category_id) for category_id in request.form.getlist("categories")
        }
    except ValueError:
        return None

    available_ids = {category.category_id for category in categories}

    return selected_ids if selected_ids <= available_ids else None


def _can_view_event(event):
    """Apply event lifecycle and privacy rules to detail and image access."""

    if g.user is None:
        return event.status == "Published" and event.privacy == "Public"

    if event.organiser_id == g.user.user_id:
        return True

    attendance = db.session.get(
        Attendance,
        (g.user.user_id, event.event_id),
    )

    if event.status == "Cancelled":
        return attendance is not None

    if event.status != "Published":
        return False

    if event.privacy == "Public" or (
        attendance is not None and attendance.status != "Revoked"
    ):
        return True

    if attendance is not None and attendance.status == "Revoked":
        return False

    token = session.get(f"private_event_{event.event_id}")
    return (
        token
        and token == event.invite_token
        and event.invite_expires_at
        and event.invite_expires_at >= datetime.now()
    )


def _invited_email_set(event):
    return {
        email.casefold()
        for email in re.split(r"[\s,;]+", event.invited_emails or "")
        if email
    }


def _private_attendance_response(event_id, attendance, message):
    """Return the updated private-attendance state for an in-page action."""

    counts = dict.fromkeys(("Pending", "Going", "Declined", "Revoked"), 0)
    for status, count in db.session.execute(
        select(Attendance.status, func.count())
        .where(Attendance.event_id == event_id)
        .group_by(Attendance.status)
    ):
        if status in counts:
            counts[status] = count

    if attendance.status == "Pending":
        actions = [
            {
                "label": "Approve",
                "url": url_for(
                    "events.decide_attendance_request",
                    event_id=event_id,
                    user_id=attendance.user_id,
                    decision="approve",
                ),
                "class_name": "button-success",
            },
            {
                "label": "Decline",
                "url": url_for(
                    "events.decide_attendance_request",
                    event_id=event_id,
                    user_id=attendance.user_id,
                    decision="decline",
                ),
                "class_name": "button-secondary",
            },
        ]
    elif attendance.status == "Revoked":
        actions = [
            {
                "label": "Restore as Pending",
                "url": url_for(
                    "events.manage_private_access",
                    event_id=event_id,
                    user_id=attendance.user_id,
                    action="restore",
                ),
                "class_name": "button-secondary",
            }
        ]
    else:
        actions = [
            {
                "label": "Revoke Access",
                "url": url_for(
                    "events.manage_private_access",
                    event_id=event_id,
                    user_id=attendance.user_id,
                    action="revoke",
                ),
                "class_name": "button-secondary",
            }
        ]

    return jsonify(
        message=message,
        status=attendance.status,
        status_label="Approved" if attendance.status == "Going" else attendance.status,
        counts=counts,
        actions=actions,
    )


@events.route("/manage-events")
@login_required
def manage_events():

    # Count registrations once and join the totals to every organised event
    attendance_counts = (
        select(
            Attendance.event_id,
            func.count(Attendance.user_id).label("attendee_count"),
        )
        .where(Attendance.status == "Going")
        .group_by(Attendance.event_id)
        .subquery()
    )

    event_rows = db.session.execute(
        select(
            Event,
            func.coalesce(attendance_counts.c.attendee_count, 0),
        )
        .outerjoin(
            attendance_counts,
            attendance_counts.c.event_id == Event.event_id,
        )
        .where(Event.organiser_id == g.user.user_id)
        .options(selectinload(Event.categories))
        .order_by(Event.start_datetime)
    ).all()

    organiser_events = [row[0] for row in event_rows]

    attendee_counts = {
        event.event_id: attendee_count for event, attendee_count in event_rows
    }

    # Keep events in the upcoming list until they have finished
    current_time = datetime.now()

    upcoming_events = [
        event for event in organiser_events if event.end_datetime >= current_time
    ]

    past_events = [
        event for event in organiser_events if event.start_datetime < current_time
    ]

    # Summarize capacity without treating unlimited events as nearly full
    full_events = [
        event
        for event in organiser_events
        if event.status == "Published"
        and event.capacity is not None
        and attendee_counts[event.event_id] >= event.capacity
    ]

    nearly_full_events = [
        event
        for event in organiser_events
        if event.status == "Published"
        and event.capacity is not None
        and event.capacity > 0
        and attendee_counts[event.event_id] < event.capacity
        and attendee_counts[event.event_id] / event.capacity >= NEARLY_FULL_THRESHOLD
    ]

    summary = {
        "total_events": len(organiser_events),
        "published_events": sum(
            event.status == "Published" for event in organiser_events
        ),
        "draft_events": sum(event.status == "Draft" for event in organiser_events),
        "cancelled_events": sum(
            event.status == "Cancelled" for event in organiser_events
        ),
        "upcoming_events": len(upcoming_events),
        "past_events": len(past_events),
        "total_registrations": sum(attendee_counts.values()),
        "full_events": len(full_events),
        "nearly_full_events": len(nearly_full_events),
    }

    # Display the organiser dashboard using the aggregated event information
    return render_template(
        "manage_events.html",
        upcoming_events=upcoming_events,
        past_events=past_events,
        attendee_counts=attendee_counts,
        summary=summary,
        nearly_full_threshold=int(NEARLY_FULL_THRESHOLD * 100),
    )


@events.route("/my-events")
@login_required
def my_events():

    # Keep cancelled registrations visible while excluding organiser-only drafts
    attending_events = db.session.scalars(
        select(Event)
        .join(Attendance)
        .where(
            Attendance.user_id == g.user.user_id,
            Attendance.status == "Going",
            Event.status.in_(("Published", "Cancelled")),
        )
        .options(selectinload(Event.categories), selectinload(Event.attendees))
        .order_by(
            Event.end_datetime < datetime.now(),
            Event.status == "Cancelled",
            Event.start_datetime,
        )
    ).all()

    favourite_events = db.session.scalars(
        select(Event)
        .join(Favourite)
        .where(
            Favourite.user_id == g.user.user_id,
            Event.privacy == "Public",
            Event.status.in_(("Published", "Cancelled")),
        )
        .options(selectinload(Event.categories), selectinload(Event.attendees))
        .order_by(Event.start_datetime)
    ).all()

    return render_template(
        "my_events.html",
        events=attending_events,
        favourite_events=favourite_events,
    )


def _confirmed_attendance_or_404(event_id, user_id):
    """Return one confirmed registration without exposing other tickets."""

    attendance = db.session.scalar(
        select(Attendance)
        .where(
            Attendance.event_id == event_id,
            Attendance.user_id == user_id,
            Attendance.status == "Going",
        )
        .options(selectinload(Attendance.event), selectinload(Attendance.user))
    )
    if attendance is None:
        abort(404)
    return attendance


@events.route("/my-events/<int:event_id>/ticket")
@login_required
def attendee_ticket(event_id):
    """Show the attendee's confirmation and QR ticket preview."""

    attendance = _confirmed_attendance_or_404(event_id, g.user.user_id)
    return render_template("attendee_ticket.html", attendance=attendance)


@events.route("/my-events/<int:event_id>/ticket.png")
@login_required
def attendee_ticket_qr(event_id):
    """Render a QR ticket owned by the logged-in attendee."""

    attendance = _confirmed_attendance_or_404(event_id, g.user.user_id)
    check_in_url = url_for(
        "events.check_in_attendee",
        event_id=event_id,
        ticket=attendance.ticket_token,
        _external=True,
    )
    image = qrcode.make(check_in_url)
    output = BytesIO()
    image.save(output, format="PNG")
    response = Response(output.getvalue(), mimetype="image/png")
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@events.route("/events/<int:event_id>/check-in", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["ORGANISER_ACTION_RATE_LIMIT"], methods=["POST"]
)
@login_required
def check_in_attendee(event_id):
    """Let an organiser search, verify, check in, and undo attendee check-ins."""

    event = _owned_event_or_404(event_id)
    search = request.args.get("search", "").strip()
    action = request.form.get("action", "check_in")
    ticket_token = (
        request.form.get("ticket", "")
        if request.method == "POST"
        else request.args.get("ticket", "")
    ).strip()
    selected_user_id = request.form.get("user_id", type=int)
    attendance = None
    if selected_user_id is not None:
        attendance = db.session.scalar(
            select(Attendance)
            .where(
                Attendance.event_id == event_id,
                Attendance.user_id == selected_user_id,
                Attendance.status == "Going",
            )
            .options(selectinload(Attendance.user))
        )
    elif ticket_token:
        attendance = db.session.scalar(
            select(Attendance)
            .where(
                Attendance.event_id == event_id,
                Attendance.ticket_token == ticket_token,
                Attendance.status == "Going",
            )
            .options(selectinload(Attendance.user))
        )

    if request.method == "POST":
        if attendance is None:
            flash("That ticket or attendee is invalid for this event.", "error")
        elif event.status == "Cancelled":
            flash("Check-in is unavailable because this event is cancelled.", "warning")
        elif action == "undo":
            if attendance.checked_in_at is None:
                flash("This attendee has not been checked in yet.", "info")
            else:
                attendance.checked_in_at = None
                db.session.commit()
                flash("Attendee check-in was undone.", "success")
        elif attendance.checked_in_at is not None:
            flash("This ticket has already been checked in.", "warning")
        else:
            attendance.checked_in_at = datetime.now(UTC)
            db.session.commit()
            flash("Attendee checked in successfully.", "success")
        return redirect(url_for("events.check_in_attendee", event_id=event_id))

    attendances = db.session.scalars(
        select(Attendance)
        .where(
            Attendance.event_id == event_id,
            Attendance.status == "Going",
        )
        .options(selectinload(Attendance.user))
        .order_by(Attendance.registered_at, Attendance.user_id)
    ).all()
    if search:
        search_text = search.casefold()
        attendances = [
            item
            for item in attendances
            if search_text
            in f"{item.user.first_name} {item.user.last_name} {item.user.username}".casefold()
        ]
    total_attendees = db.session.scalar(
        select(func.count())
        .select_from(Attendance)
        .where(Attendance.event_id == event_id, Attendance.status == "Going")
    )
    checked_in_count = db.session.scalar(
        select(func.count())
        .select_from(Attendance)
        .where(
            Attendance.event_id == event_id,
            Attendance.status == "Going",
            Attendance.checked_in_at.is_not(None),
        )
    )

    return render_template(
        "event_check_in.html",
        event=event,
        attendance=attendance,
        ticket_token=ticket_token,
        attendances=attendances,
        search=search,
        total_attendees=total_attendees,
        checked_in_count=checked_in_count,
    )


@events.route("/favourites")
@login_required
def favourites():
    """Display all public events saved by the current user."""

    favourite_events = db.session.scalars(
        select(Event)
        .join(Favourite)
        .where(
            Favourite.user_id == g.user.user_id,
            Event.privacy == "Public",
            Event.status.in_(("Published", "Cancelled")),
        )
        .options(selectinload(Event.categories), selectinload(Event.attendees))
        .order_by(Event.start_datetime)
    ).all()

    return render_template("favourites.html", events=favourite_events)


@events.route("/events/<int:event_id>/favourite", methods=["POST"])
@limiter.limit(lambda: current_app.config["ACCOUNT_ACTION_RATE_LIMIT"])
@login_required
def toggle_favourite(event_id):
    """Save or remove one accessible public event from the user's favourites."""

    event = db.get_or_404(Event, event_id)
    if event.privacy != "Public" or event.status not in ("Published", "Cancelled"):
        abort(403)

    favourite = db.session.get(Favourite, (g.user.user_id, event_id))
    if favourite is None:
        db.session.add(Favourite(user_id=g.user.user_id, event_id=event_id))
        message = "Event added to your favourites."
    else:
        db.session.delete(favourite)
        message = "Event removed from your favourites."

    db.session.commit()

    if request.accept_mimetypes.best == "application/json":
        return jsonify(
            event_id=event_id,
            is_favourite=favourite is None,
            message=message,
        )

    flash(message, "success")

    destination = request.form.get("next", "")
    if not destination.startswith("/") or destination.startswith("//"):
        destination = url_for("events.event_details", event_id=event_id)
    return redirect(destination)


@events.route("/calendar")
@login_required
def calendar():
    """Show attended and organised events in an interactive month grid."""

    today = date.today()
    requested_year = request.args.get("year", type=int)
    requested_month = request.args.get("month", type=int)
    year = requested_year if requested_year is not None else today.year
    month = requested_month if requested_month is not None else today.month
    if year < 1900 or year > 2100 or month < 1 or month > 12:
        abort(404)

    relevant_events = db.session.scalars(
        select(Event)
        .outerjoin(
            Attendance,
            (Attendance.event_id == Event.event_id)
            & (Attendance.user_id == g.user.user_id)
            & (Attendance.status == "Going"),
        )
        .where(
            or_(
                Event.organiser_id == g.user.user_id,
                Attendance.user_id == g.user.user_id,
            ),
            or_(
                Event.organiser_id == g.user.user_id,
                Event.status.in_(("Published", "Cancelled")),
            ),
        )
        .options(selectinload(Event.categories), selectinload(Event.attendees))
        .order_by(Event.start_datetime, Event.event_id)
    ).all()

    events_by_date = {}
    for event in relevant_events:
        events_by_date.setdefault(event.start_datetime.date(), []).append(event)

    calendar_days = [
        {
            "date": day,
            "in_month": day.month == month,
            "is_today": day == today,
            "events": events_by_date.get(day, []),
        }
        for day in Calendar(firstweekday=0).itermonthdates(year, month)
    ]

    previous_month = 12 if month == 1 else month - 1
    previous_year = year - 1 if month == 1 else year
    next_month = 1 if month == 12 else month + 1
    next_year = year + 1 if month == 12 else year

    return render_template(
        "calendar.html",
        calendar_days=calendar_days,
        calendar_title=f"{month_name[month]} {year}",
        previous_month=previous_month,
        previous_year=previous_year,
        next_month=next_month,
        next_year=next_year,
        today=today,
    )


@events.route("/events")
def browse_events():

    # Retrieve the user's search and filter selections
    search = request.args.get("search", "").strip()

    # Retrieve all valid selected category identifiers.
    selected_category_ids = set(request.args.getlist("category", type=int))

    # Retrieve the selected city
    selected_city = request.args.get("city", "").strip()

    # Retrieve all categories for the filter dropdown
    categories = Category.query.order_by(Category.name).all()

    # Retrieve all unique cities that have public events
    cities = db.session.scalars(
        select(Event.city)
        .where(
            Event.privacy == "Public",
            Event.status == "Published",
            Event.end_datetime >= datetime.now(),
        )
        .distinct()
        .order_by(Event.city)
    ).all()

    # Public discovery includes only published public events
    statement = (
        select(Event)
        .where(
            Event.privacy == "Public",
            Event.status == "Published",
            Event.end_datetime >= datetime.now(),
        )
        .options(selectinload(Event.categories), selectinload(Event.attendees))
    )

    # Match events assigned to any of the selected categories.
    if selected_category_ids:
        statement = (
            statement.join(EventCategory)
            .where(EventCategory.category_id.in_(selected_category_ids))
            .distinct()
        )

    # Filter events by city
    if selected_city:
        statement = statement.where(Event.city == selected_city)

    # Match event details and modest misspellings before database pagination.
    if search:
        matching_event_ids = [
            event.event_id
            for event in db.session.scalars(statement).unique().all()
            if _event_matches_search(event, search)
        ]
        statement = statement.where(Event.event_id.in_(matching_event_ids))

    # Retrieve only the requested page while retaining chronological ordering
    pagination = db.paginate(
        statement.order_by(Event.start_datetime),
        per_page=current_app.config["EVENTS_PER_PAGE"],
        max_per_page=50,
    )

    selected_category_list = sorted(selected_category_ids)
    active_filters = []
    if search:
        active_filters.append(
            {
                "label": f"Search: “{search}”",
                "remove_url": url_for(
                    "events.browse_events",
                    category=selected_category_list or None,
                    city=selected_city or None,
                ),
            }
        )
    if selected_city:
        active_filters.append(
            {
                "label": selected_city,
                "remove_url": url_for(
                    "events.browse_events",
                    search=search or None,
                    category=selected_category_list or None,
                ),
            }
        )
    category_by_id = {category.category_id: category for category in categories}
    for category_id in selected_category_list:
        category = category_by_id.get(category_id)
        if category is None:
            continue
        remaining_categories = [
            selected_id
            for selected_id in selected_category_list
            if selected_id != category_id
        ]
        active_filters.append(
            {
                "label": f"#{category.name}",
                "remove_url": url_for(
                    "events.browse_events",
                    search=search or None,
                    category=remaining_categories or None,
                    city=selected_city or None,
                ),
            }
        )

    # Display the public events page
    return render_template(
        "browse_events.html",
        events=pagination.items,
        pagination=pagination,
        categories=categories,
        cities=cities,
        search=search,
        selected_category_ids=selected_category_ids,
        selected_city=selected_city,
        active_filters=active_filters,
    )


@events.route("/events/<int:event_id>")
@limiter.limit(lambda: current_app.config["PRIVATE_LINK_RATE_LIMIT"])
def event_details(event_id):

    # Retrieve the event and relationships required by the details page
    event = db.first_or_404(
        select(Event)
        .where(Event.event_id == event_id)
        .options(
            selectinload(Event.categories),
            selectinload(Event.attendees).selectinload(Attendance.user),
        )
    )

    invite_token = request.args.get("invite", "")
    if event.privacy == "Private" and invite_token:
        valid_link = (
            secrets.compare_digest(invite_token, event.invite_token or "")
            and event.invite_expires_at is not None
            and event.invite_expires_at >= datetime.now()
        )
        if not valid_link:
            abort(403)
        if g.user is None:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        invited_emails = _invited_email_set(event)
        if invited_emails and g.user.email.casefold() not in invited_emails:
            abort(403)
        existing_attendance = db.session.get(
            Attendance, (g.user.user_id, event.event_id)
        )
        if existing_attendance is not None and existing_attendance.status == "Revoked":
            abort(403)
        session[f"private_event_{event.event_id}"] = event.invite_token
        return redirect(url_for("events.event_details", event_id=event.event_id))

    # Apply status and privacy authorization before rendering event data
    if not _can_view_event(event):
        abort(403)

    # Derive attendance controls from the eagerly loaded attendance records
    attendee_count = sum(attendance.status == "Going" for attendance in event.attendees)
    organiser_attendances = sorted(
        event.attendees,
        key=lambda attendance: (
            {"Pending": 0, "Going": 1, "Declined": 2, "Revoked": 3}.get(
                attendance.status, 4
            ),
            attendance.registered_at,
        ),
    )
    attendance_status_counts = {
        status: sum(item.status == status for item in event.attendees)
        for status in ("Pending", "Going", "Declined", "Revoked")
    }

    current_attendance = next(
        (
            attendance
            for attendance in event.attendees
            if g.user is not None and attendance.user_id == g.user.user_id
        ),
        None,
    )
    is_attending = (
        current_attendance is not None and current_attendance.status == "Going"
    )

    is_full = event.capacity is not None and attendee_count >= event.capacity
    preview_mode = (
        request.args.get("preview") == "attendee"
        and g.user is not None
        and event.organiser_id == g.user.user_id
    )
    share_url = url_for("events.event_details", event_id=event.event_id, _external=True)
    map_destination = _event_map_destination(event)

    response = make_response(
        render_template(
            "event_details.html",
            event=event,
            attendee_count=attendee_count,
            organiser_attendances=organiser_attendances,
            attendance_status_counts=attendance_status_counts,
            is_attending=is_attending,
            is_full=is_full,
            current_attendance=current_attendance,
            preview_mode=preview_mode,
            share_url=share_url,
            whatsapp_share_url=(
                "https://wa.me/?" + urlencode({"text": f"{event.title} · {share_url}"})
                if event.privacy == "Public"
                else None
            ),
            map_embed_url=(
                "https://www.google.com/maps?"
                + urlencode({"q": map_destination, "output": "embed"})
                if map_destination
                else None
            ),
            registration_closed=(
                not event.requests_open
                or event.end_datetime <= datetime.now()
                or (
                    event.registration_deadline is not None
                    and event.registration_deadline <= datetime.now()
                )
            ),
            invite_url=(
                url_for(
                    "events.event_details",
                    event_id=event.event_id,
                    invite=event.invite_token,
                    _external=True,
                )
                if g.user is not None
                and event.organiser_id == g.user.user_id
                and event.privacy == "Private"
                else None
            ),
        )
    )
    if event.privacy == "Private" or event.status != "Published":
        response.headers["Cache-Control"] = "private, no-store"
    return response


@events.route("/events/<int:event_id>/preview")
@login_required
def preview_event(event_id):
    """Open an organiser-owned event with attendee-facing controls hidden."""

    _owned_event_or_404(event_id)
    return redirect(
        url_for("events.event_details", event_id=event_id, preview="attendee")
    )


@events.route("/events/<int:event_id>/directions/<provider>")
def event_directions(event_id, provider):
    """Open an accessible event location in a trusted map provider."""

    event = db.get_or_404(Event, event_id)
    if not _can_view_event(event):
        abort(403)

    destination = _event_map_destination(event)
    if provider == "google":
        map_url = "https://www.google.com/maps/dir/?" + urlencode(
            {"api": 1, "destination": destination}
        )
    elif provider == "apple":
        map_url = "https://maps.apple.com/?" + urlencode({"daddr": destination})
    else:
        abort(404)
    return redirect(map_url)


@events.route("/event-images/<path:filename>")
def event_image(filename):

    # Resolve image access through its owning event instead of trusting a path
    if filename != filename.rsplit("/", 1)[-1]:
        abort(404)

    event = db.session.scalar(select(Event).where(Event.image_path == filename))

    if event is None:
        abort(404)

    if not _can_view_event(event):
        abort(403)

    response = send_from_directory(
        current_app.config["EVENT_IMAGE_UPLOAD_FOLDER"],
        filename,
        max_age=current_app.config["EVENT_IMAGE_CACHE_SECONDS"],
    )

    response.headers["X-Content-Type-Options"] = "nosniff"
    if event.privacy == "Private" or event.status != "Published":
        response.headers["Cache-Control"] = "private, no-store"

    return response


@events.route("/events/<int:event_id>/calendar.ics")
def download_event_calendar(event_id):
    """Download one accessible event as a portable iCalendar file."""

    event = db.get_or_404(Event, event_id)
    if not _can_view_event(event):
        abort(403)

    location = _event_calendar_location(event)
    event_url = url_for(
        "events.event_details",
        event_id=event.event_id,
        _external=True,
    )
    calendar = "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//eventid//Event Calendar//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VEVENT",
            f"UID:event-{event.event_id}@eventid",
            f"DTSTAMP:{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{_ics_utc(event.start_datetime)}",
            f"DTEND:{_ics_utc(event.end_datetime)}",
            f"SUMMARY:{_ics_escape(event.title)}",
            f"DESCRIPTION:{_ics_escape(event.description)}",
            f"LOCATION:{_ics_escape(location)}",
            f"URL:{_ics_escape(event_url)}",
            f"STATUS:{'CANCELLED' if event.status == 'Cancelled' else 'CONFIRMED'}",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )
    return Response(
        calendar,
        mimetype="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="event-{event.event_id}.ics"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@events.route("/events/<int:event_id>/calendar/<provider>")
def open_event_calendar(event_id, provider):
    """Open an accessible event in a supported web calendar."""

    event = db.get_or_404(Event, event_id)
    if not _can_view_event(event):
        abort(403)

    event_url = url_for("events.event_details", event_id=event.event_id, _external=True)
    description = f"{event.description}\n\n{event_url}"
    location = _event_calendar_location(event)

    if provider == "google":
        query = urlencode(
            {
                "action": "TEMPLATE",
                "text": event.title,
                "dates": f"{_ics_utc(event.start_datetime)}/{_ics_utc(event.end_datetime)}",
                "details": description,
                "location": location,
            }
        )
        destination = f"https://calendar.google.com/calendar/render?{query}"
    elif provider == "outlook":
        query = urlencode(
            {
                "path": "/calendar/action/compose",
                "rru": "addevent",
                "subject": event.title,
                "startdt": _calendar_iso(event.start_datetime),
                "enddt": _calendar_iso(event.end_datetime),
                "body": description,
                "location": location,
            }
        )
        destination = f"https://outlook.live.com/calendar/0/deeplink/compose?{query}"
    else:
        abort(404)

    return redirect(destination)


def _locked_event(event_id):
    """Lock attendance writes for an event before capacity is checked."""

    dialect = db.session.get_bind().dialect.name

    if dialect == "sqlite":

        # End the earlier user lookup before reserving SQLite's writer lock
        db.session.rollback()

        # Serialize the capacity check and insert with SQLite's write lock
        db.session.execute(text("BEGIN IMMEDIATE"))

        return db.session.get(
            Event,
            event_id,
        )

    # Serialize registrations for this event using a database row lock
    return db.session.scalar(
        select(Event)
        .where(Event.event_id == event_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


@events.route("/events/<int:event_id>/attend", methods=["POST"])
@limiter.limit(lambda: current_app.config["ATTENDANCE_RATE_LIMIT"])
def attend_event(event_id):

    if g.user is None:

        flash(
            "Please log in or create an account to attend this event.",
            "info",
        )

        destination = url_for(
            "events.event_details",
            event_id=event_id,
        )

        return redirect(
            url_for(
                "auth.login",
                next=destination,
            )
        )

    user_id = g.user.user_id

    destination = url_for(
        "events.event_details",
        event_id=event_id,
    )

    try:

        # Lock the capacity decision before reading or creating attendance
        event = _locked_event(event_id)

        if event is None:

            # Release the explicit lock before returning a missing-event response
            db.session.rollback()

            abort(404)

        # Private requests require a valid invite link stored by the detail page.
        if event.privacy != "Public" and not _can_view_event(event):

            db.session.rollback()

            abort(403)

        # Only published events can accept new attendance registrations
        if event.status != "Published":

            db.session.rollback()

            flash(
                "This event is not accepting new registrations.",
                "warning",
            )

            return redirect(destination)

        if (
            event.end_datetime <= datetime.now()
            or not event.requests_open
            or (
                event.registration_deadline is not None
                and event.registration_deadline <= datetime.now()
            )
        ):
            db.session.rollback()
            flash("Registration for this event has closed.", "warning")
            return redirect(destination)

        # Keep the organiser separate from ordinary attendance records
        if event.organiser_id == user_id:

            db.session.rollback()

            flash(
                "Organisers cannot register as attendees for their own events.",
                "warning",
            )

            return redirect(destination)

        # Avoid duplicate attendance before relying on the database constraint
        existing = db.session.get(
            Attendance,
            (user_id, event_id),
        )

        if existing is not None:

            db.session.rollback()

            flash(
                "You are already attending this event.",
                "info",
            )

            return redirect(destination)

        # Count registrations while the event capacity decision remains locked
        attendee_count = db.session.scalar(
            select(func.count())
            .select_from(Attendance)
            .where(
                Attendance.event_id == event_id,
                Attendance.status == "Going",
            )
        )

        # Treat missing capacity as unlimited and reject full or overfull events
        if event.capacity is not None and attendee_count >= event.capacity:

            db.session.rollback()

            flash(
                "This event is full.",
                "warning",
            )

            return redirect(destination)

        attendance = Attendance(
            user_id=user_id,
            event_id=event_id,
            status="Pending" if event.privacy == "Private" else "Going",
        )
        db.session.add(attendance)

        db.session.commit()

    except IntegrityError:

        # Handle a duplicate that reaches the composite primary-key constraint
        db.session.rollback()

        flash(
            "You are already attending this event.",
            "info",
        )

        return redirect(destination)

    except OperationalError:

        # Release failed locks or transactions before allowing a safe retry
        db.session.rollback()

        flash(
            "Attendance is busy. Please try again.",
            "error",
        )

        return redirect(destination)

    except SQLAlchemyError:

        # Keep the session usable after any other attendance database failure
        db.session.rollback()

        flash(
            "Attendance could not be saved. Please try again.",
            "error",
        )

        return redirect(destination)

    flash(
        (
            "Your attendance request is pending organiser approval."
            if event.privacy == "Private"
            else "You are now attending this event."
        ),
        "success",
    )

    return redirect(destination)


@events.route("/events/<int:event_id>/leave", methods=["POST"])
@limiter.limit(lambda: current_app.config["ATTENDANCE_RATE_LIMIT"])
@login_required
def leave_event(event_id):

    # Retrieve the selected event or return a 404 error if it does not exist
    event = db.get_or_404(
        Event,
        event_id,
    )

    destination = url_for(
        "events.event_details",
        event_id=event_id,
    )

    # Allow authorised existing attendees to leave cancelled private events
    if not _can_view_event(event):
        abort(403)

    attendance = db.session.get(
        Attendance,
        (g.user.user_id, event_id),
    )

    if attendance is None:

        flash(
            "You are not registered for this event.",
            "info",
        )

        return redirect(destination)

    try:

        db.session.delete(attendance)

        db.session.commit()

    except SQLAlchemyError:

        # Restore the session after a failed attendance deletion
        db.session.rollback()

        flash(
            "Your registration could not be removed. Please try again.",
            "error",
        )

        return redirect(destination)

    flash(
        "You are no longer attending this event.",
        "success",
    )

    return redirect(destination)


@events.route("/my-attending-events")
@login_required
def my_attending_events():

    # Preserve existing bookmarks while keeping one attendance-page query
    return redirect(url_for("events.my_events"))


@events.route("/events/create", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["ORGANISER_ACTION_RATE_LIMIT"], methods=["POST"]
)
@login_required
def create_event():

    form = EventForm()

    categories = Category.query.order_by(Category.name).all()

    if form.validate_on_submit():

        selected_category_ids = _category_ids(categories)

        if selected_category_ids is None:

            flash(
                "One or more selected categories are invalid.",
                "error",
            )

            return render_template(
                "event_form.html",
                form=form,
                categories=categories,
                selected_category_ids=set(),
                page_title="Create Event",
            )

        image_extension, image_error = validate_event_image(form.image.data)

        if image_error:

            form.image.errors.append(image_error)

        else:

            saved_image = None

            try:

                if image_extension:

                    # Save under a generated filename before the transaction
                    saved_image = save_event_image(
                        form.image.data,
                        image_extension,
                        (
                            50
                            if form.image_crop_x.data is None
                            else form.image_crop_x.data
                        ),
                        (
                            50
                            if form.image_crop_y.data is None
                            else form.image_crop_y.data
                        ),
                    )

                event = Event(
                    title=form.title.data,
                    description=form.description.data or "",
                    venue_name=form.venue_name.data,
                    address=form.address.data,
                    postcode=form.postcode.data,
                    city=form.city.data,
                    country=form.country.data,
                    location_notes=form.location_notes.data,
                    start_datetime=form.start_datetime.data,
                    end_datetime=form.end_datetime.data,
                    capacity=form.capacity.data,
                    registration_deadline=form.registration_deadline.data,
                    latitude=form.latitude.data,
                    longitude=form.longitude.data,
                    privacy=form.privacy.data,
                    invite_token=(
                        secrets.token_urlsafe(32)
                        if form.privacy.data == "Private"
                        else None
                    ),
                    invite_expires_at=(
                        form.invite_expires_at.data
                        if form.privacy.data == "Private"
                        else None
                    ),
                    invited_emails=(
                        form.invited_emails.data
                        if form.privacy.data == "Private"
                        else None
                    ),
                    requests_open=form.requests_open.data,
                    status=form.status.data,
                    image_path=saved_image,
                    organiser_id=g.user.user_id,
                )

                db.session.add(event)

                db.session.flush()

                for category_id in selected_category_ids:

                    db.session.add(
                        EventCategory(
                            event_id=event.event_id,
                            category_id=category_id,
                        )
                    )

                db.session.commit()

            except (OSError, SQLAlchemyError):

                # Roll back data and remove a newly saved orphan image
                db.session.rollback()

                delete_event_image(saved_image)

                flash(
                    "The event could not be created. Please try again.",
                    "error",
                )

            else:

                flash(
                    "Event created successfully.",
                    "success",
                )

                return redirect(url_for("events.manage_events"))

    return render_template(
        "event_form.html",
        form=form,
        categories=categories,
        selected_category_ids=set(request.form.getlist("categories")),
        page_title="Create Event",
    )


@events.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["ORGANISER_ACTION_RATE_LIMIT"], methods=["POST"]
)
@login_required
def edit_event(event_id):

    event = _owned_event_or_404(event_id)

    form = EventForm(obj=event)

    categories = Category.query.order_by(Category.name).all()

    selected_category_ids = {link.category_id for link in event.event_categories}

    if form.validate_on_submit():

        submitted_category_ids = _category_ids(categories)

        if submitted_category_ids is None:

            flash(
                "One or more selected categories are invalid.",
                "error",
            )

        else:

            attendee_count = db.session.scalar(
                select(func.count())
                .select_from(Attendance)
                .where(
                    Attendance.event_id == event.event_id,
                    Attendance.status == "Going",
                )
            )

            # Prevent organisers from reducing capacity below attendance
            if form.capacity.data is not None and form.capacity.data < attendee_count:

                form.capacity.errors.append(
                    f"Capacity cannot be lower than the {attendee_count} "
                    "existing attendees."
                )

            else:

                image_extension, image_error = validate_event_image(form.image.data)

                if image_error:

                    form.image.errors.append(image_error)

                else:

                    old_image = event.image_path

                    new_image = None

                    try:

                        if image_extension:

                            new_image = save_event_image(
                                form.image.data,
                                image_extension,
                                (
                                    50
                                    if form.image_crop_x.data is None
                                    else form.image_crop_x.data
                                ),
                                (
                                    50
                                    if form.image_crop_y.data is None
                                    else form.image_crop_y.data
                                ),
                            )

                        event.title = form.title.data

                        event.description = form.description.data or ""

                        event.venue_name = form.venue_name.data

                        event.address = form.address.data

                        event.postcode = form.postcode.data

                        event.city = form.city.data

                        event.country = form.country.data

                        event.location_notes = form.location_notes.data

                        event.latitude = form.latitude.data

                        event.longitude = form.longitude.data

                        event.start_datetime = form.start_datetime.data

                        event.end_datetime = form.end_datetime.data

                        event.capacity = form.capacity.data

                        event.registration_deadline = form.registration_deadline.data

                        event.privacy = form.privacy.data

                        if event.privacy == "Private":
                            event.invite_token = (
                                event.invite_token or secrets.token_urlsafe(32)
                            )
                            event.invite_expires_at = form.invite_expires_at.data
                            event.invited_emails = form.invited_emails.data
                        else:
                            event.invite_token = None
                            event.invite_expires_at = None
                            event.invited_emails = None

                        event.requests_open = form.requests_open.data

                        event.status = form.status.data

                        if new_image:

                            event.image_path = new_image

                        elif form.remove_image.data:

                            event.image_path = None

                        # Replace category associations in the same transaction
                        event.event_categories.clear()

                        event.event_categories.extend(
                            EventCategory(category_id=category_id)
                            for category_id in submitted_category_ids
                        )

                        db.session.commit()

                    except (OSError, SQLAlchemyError):

                        db.session.rollback()

                        delete_event_image(new_image)

                        flash(
                            "The event could not be updated. Please try again.",
                            "error",
                        )

                    else:

                        if old_image and (new_image or form.remove_image.data):

                            delete_event_image(old_image)

                        flash(
                            "Event updated successfully.",
                            "success",
                        )

                        return redirect(url_for("events.manage_events"))

        selected_category_ids = set(request.form.getlist("categories"))

    return render_template(
        "event_form.html",
        form=form,
        categories=categories,
        selected_category_ids=selected_category_ids,
        event=event,
        page_title="Edit Event",
    )


@events.route("/events/<int:event_id>/duplicate", methods=["POST"])
@limiter.limit(lambda: current_app.config["ORGANISER_ACTION_RATE_LIMIT"])
@login_required
def duplicate_event(event_id):
    """Create an editable draft copy without attendees, tickets, or image reuse."""

    source = _owned_event_or_404(event_id)
    invite_expiry = source.invite_expires_at
    if source.privacy == "Private" and (
        invite_expiry is None or invite_expiry <= datetime.now()
    ):
        invite_expiry = datetime.now() + timedelta(days=7)

    duplicate = Event(
        title=f"Copy of {source.title}"[:100],
        description=source.description,
        venue_name=source.venue_name,
        address=source.address,
        postcode=source.postcode,
        city=source.city,
        country=source.country,
        location_notes=source.location_notes,
        latitude=source.latitude,
        longitude=source.longitude,
        start_datetime=source.start_datetime,
        end_datetime=source.end_datetime,
        capacity=source.capacity,
        registration_deadline=source.registration_deadline,
        privacy=source.privacy,
        invite_token=(
            secrets.token_urlsafe(32) if source.privacy == "Private" else None
        ),
        invite_expires_at=invite_expiry if source.privacy == "Private" else None,
        invited_emails=source.invited_emails,
        requests_open=False,
        status="Draft",
        image_path=None,
        organiser_id=g.user.user_id,
    )
    duplicate.event_categories.extend(
        EventCategory(category_id=link.category_id) for link in source.event_categories
    )
    db.session.add(duplicate)
    db.session.commit()
    flash(
        "Draft copy created. Review its dates and details before publishing.", "success"
    )
    return redirect(url_for("events.edit_event", event_id=duplicate.event_id))


@events.route("/events/<int:event_id>/status", methods=["POST"])
@limiter.limit(lambda: current_app.config["ORGANISER_ACTION_RATE_LIMIT"])
@login_required
def change_event_status(event_id):

    event = _owned_event_or_404(event_id)

    new_status = request.form.get("status")

    if new_status not in EVENT_STATUSES:
        abort(400)

    try:

        event.status = new_status

        db.session.commit()

    except SQLAlchemyError:

        db.session.rollback()

        flash(
            "The event status could not be changed.",
            "error",
        )

    else:

        flash(
            f"Event status changed to {new_status}.",
            "success",
        )

    return redirect(url_for("events.manage_events"))


@events.route(
    "/events/<int:event_id>/requests/<int:user_id>/<decision>", methods=["POST"]
)
@limiter.limit(lambda: current_app.config["ORGANISER_ACTION_RATE_LIMIT"])
@login_required
def decide_attendance_request(event_id, user_id, decision):
    """Approve or decline one pending private-event request."""

    if decision not in {"approve", "decline"}:
        abort(400)

    # Serialize approval/decline with ordinary registration for this event.
    event = _owned_event_or_404(event_id, lock=True)

    attendance = db.session.get(Attendance, (user_id, event_id))
    if attendance is None or attendance.status != "Pending":
        abort(404)

    if decision == "approve":
        confirmed_count = db.session.scalar(
            select(func.count())
            .select_from(Attendance)
            .where(
                Attendance.event_id == event_id,
                Attendance.status == "Going",
            )
        )
        if event.capacity is not None and confirmed_count >= event.capacity:
            db.session.rollback()
            if request.accept_mimetypes.best == "application/json":
                return jsonify(error="This event is already full."), 409
            flash(
                "This event is already full; the request was not approved.", "warning"
            )
            return redirect(url_for("events.event_details", event_id=event_id))
        attendance.status = "Going"
        message = "Attendance request approved."
    else:
        attendance.status = "Declined"
        message = "Attendance request declined."

    db.session.commit()
    if request.accept_mimetypes.best == "application/json":
        return _private_attendance_response(event_id, attendance, message)
    flash(message, "success")
    return redirect(url_for("events.event_details", event_id=event_id))


@events.post("/events/<int:event_id>/attendees/<int:user_id>/<action>")
@limiter.limit(lambda: current_app.config["ORGANISER_ACTION_RATE_LIMIT"])
@login_required
def manage_private_access(event_id, user_id, action):
    """Revoke or restore one person's access to an owned private event."""

    event = _owned_event_or_404(event_id)
    if event.privacy != "Private" or action not in {"revoke", "restore"}:
        abort(400)
    attendance = db.session.get(Attendance, (user_id, event_id))
    if attendance is None:
        abort(404)

    if action == "revoke":
        if attendance.status == "Revoked":
            abort(404)
        attendance.status = "Revoked"
        attendance.checked_in_at = None
        message = "Access revoked. This person can no longer open the event."
    else:
        if attendance.status != "Revoked":
            abort(404)
        attendance.status = "Pending"
        message = "Access restored as a pending request."

    db.session.commit()
    if request.accept_mimetypes.best == "application/json":
        return _private_attendance_response(event_id, attendance, message)
    flash(message, "success")
    return redirect(url_for("events.event_details", event_id=event_id))


@events.route("/events/<int:event_id>/invite/regenerate", methods=["POST"])
@limiter.limit(lambda: current_app.config["ORGANISER_ACTION_RATE_LIMIT"])
@login_required
def regenerate_invite_link(event_id):
    event = _owned_event_or_404(event_id)
    if event.privacy != "Private":
        abort(400)
    event.invite_token = secrets.token_urlsafe(32)
    db.session.commit()
    flash("The previous private link has been disabled.", "success")
    return redirect(url_for("events.event_details", event_id=event_id))


@events.route("/events/<int:event_id>/delete-confirmation")
@login_required
def confirm_delete_event(event_id):

    event = _owned_event_or_404(event_id)

    return render_template(
        "delete_event.html",
        event=event,
    )


@events.route("/events/<int:event_id>/delete", methods=["POST"])
@limiter.limit(lambda: current_app.config["ORGANISER_ACTION_RATE_LIMIT"])
@login_required
def delete_event(event_id):

    event = _owned_event_or_404(event_id)

    image_path = event.image_path

    title = event.title

    try:

        # ORM cascades remove attendance and category associations atomically
        db.session.delete(event)

        db.session.commit()

    except SQLAlchemyError:

        db.session.rollback()

        flash(
            "The event could not be deleted. Please try again.",
            "error",
        )

    else:

        delete_event_image(image_path)

        flash(
            f'Event "{title}" was deleted.',
            "success",
        )

    return redirect(url_for("events.manage_events"))


@events.route("/events/<int:event_id>/attendees/export")
@login_required
def export_attendees(event_id):

    event = _owned_event_or_404(event_id)

    attendances = db.session.scalars(
        select(Attendance)
        .where(Attendance.event_id == event.event_id)
        .options(selectinload(Attendance.user))
        .order_by(
            Attendance.registered_at,
            Attendance.user_id,
        )
    ).all()

    # Generate CSV with the standard writer to quote untrusted values safely
    output = StringIO(newline="")

    writer = csv.writer(output)

    writer.writerow(
        [
            "First name",
            "Last name",
            "Username",
            "Registration date",
            "Attendance status",
        ]
    )

    for attendance in attendances:

        writer.writerow(
            [
                _safe_csv_value(attendance.user.first_name),
                _safe_csv_value(attendance.user.last_name),
                _safe_csv_value(attendance.user.username),
                attendance.registered_at.isoformat(),
                attendance.status,
            ]
        )

    filename = f"event-{event.event_id}-attendees.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": (f'attachment; filename="{filename}"')},
    )
