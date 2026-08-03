from datetime import datetime

from flask import (
    Blueprint,
    current_app,
    render_template,
    g,
    flash,
    redirect,
    url_for,
    abort,
    request
)
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.decorators import login_required

from app.forms.event_forms import CreateEventForm
from app.database.db import db
from app.models.event import Event
from app.models.category import Category
from app.models.event_category import EventCategory
from app.models.attendance import Attendance

events = Blueprint("events", __name__)

NEARLY_FULL_THRESHOLD = 0.8


@events.route("/manage-events")
@login_required
def manage_events():
    # Count registrations once and join the totals to every organised event
    attendance_counts = (
        select(
            Attendance.event_id,
            func.count(Attendance.user_id).label("attendee_count"),
        )
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
        event.event_id: attendee_count
        for event, attendee_count in event_rows
    }

    # Separate upcoming and past events using the current local application time
    current_time = datetime.now()
    upcoming_events = [
        event for event in organiser_events
        if event.start_datetime >= current_time
    ]
    past_events = [
        event for event in organiser_events
        if event.start_datetime < current_time
    ]

    # Summarize capacity without treating unlimited events as nearly full
    full_events = [
        event for event in organiser_events
        if event.capacity is not None
        and attendee_counts[event.event_id] >= event.capacity
    ]
    nearly_full_events = [
        event for event in organiser_events
        if event.capacity is not None
        and event.capacity > 0
        and attendee_counts[event.event_id] < event.capacity
        and attendee_counts[event.event_id] / event.capacity
        >= NEARLY_FULL_THRESHOLD
    ]
    summary = {
        "total_events": len(organiser_events),
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
    # Retrieve attended events and their card categories for the current user
    attending_events = db.session.scalars(
        select(Event)
        .join(Attendance)
        .where(Attendance.user_id == g.user.user_id)
        .options(selectinload(Event.categories))
        .order_by(Event.start_datetime)
    ).all()

    return render_template(
        "my_events.html",
        events=attending_events,
    )


@events.route("/events")
@login_required
def browse_events():

    # Retrieve the user's search and filter selections
    search = request.args.get("search", "").strip()

    # Retrieve the selected category
    category_id = request.args.get("category", type=int)

    # Retrieve the selected city
    selected_city = request.args.get("city", "").strip()

    # Retrieve all categories for the filter dropdown
    categories = (
        Category.query
        .order_by(Category.name)
        .all()
    )

    # Retrieve all unique cities that have public events
    cities = db.session.scalars(
        select(Event.city)
        .where(Event.privacy == "Public")
        .distinct()
        .order_by(Event.city)
    ).all()

    # Start with all public events
    statement = (
        select(Event)
        .where(Event.privacy == "Public")
        .options(selectinload(Event.categories))
    )

    # Filter events whose titles contain the search term
    if search:

        statement = statement.where(
            Event.title.ilike(f"%{search}%")
        )

    # Filter events by category
    if category_id:

        statement = statement.join(EventCategory).where(
            EventCategory.category_id == category_id
        )

    # Filter events by city
    if selected_city:

        statement = statement.where(
            Event.city == selected_city
        )

    # Retrieve only the requested page while retaining chronological ordering
    pagination = db.paginate(
        statement.order_by(Event.start_datetime),
        per_page=current_app.config["EVENTS_PER_PAGE"],
        max_per_page=50,
    )

    # Display the public events page
    return render_template(
        "browse_events.html",
        events=pagination.items,
        pagination=pagination,
        categories=categories,
        cities=cities,
        search=search,
        selected_category=category_id,
        selected_city=selected_city
    )


@events.route("/events/<int:event_id>")
@login_required
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

    # Prevent users from viewing private events they do not organise
    if (
        event.organiser_id != g.user.user_id
        and event.privacy != "Public"
    ):

        abort(403)

    # Derive attendance controls from the eagerly loaded attendance records
    attendee_count = len(event.attendees)
    is_attending = any(
        attendance.user_id == g.user.user_id
        for attendance in event.attendees
    )
    is_full = event.capacity is not None and attendee_count >= event.capacity

    return render_template(
        "event_details.html",
        event=event,
        attendee_count=attendee_count,
        is_attending=is_attending,
        is_full=is_full,
    )


def _locked_event(event_id):
    """Lock attendance writes for an event before capacity is checked."""

    dialect = db.session.get_bind().dialect.name
    if dialect == "sqlite":
        # End the earlier user lookup before reserving SQLite's writer lock
        db.session.rollback()

        # Serialize the capacity check and insert with SQLite's write lock
        db.session.execute(text("BEGIN IMMEDIATE"))
        return db.session.get(Event, event_id)

    # Serialize registrations for this event using a database row lock
    return db.session.scalar(
        select(Event).where(Event.event_id == event_id).with_for_update()
    )


@events.route("/events/<int:event_id>/attend", methods=["POST"])
@login_required
def attend_event(event_id):
    user_id = g.user.user_id
    destination = url_for("events.event_details", event_id=event_id)

    try:
        # Lock the capacity decision before reading or creating attendance
        event = _locked_event(event_id)
        if event is None:
            # Release the explicit lock before returning a missing-event response
            db.session.rollback()
            abort(404)

        # Prevent attendance registration for inaccessible private events
        if event.privacy != "Public" and event.organiser_id != user_id:
            db.session.rollback()
            abort(403)

        # Keep the organiser separate from ordinary attendance records
        if event.organiser_id == user_id:
            db.session.rollback()
            flash("Organisers cannot register as attendees for their own events.", "warning")
            return redirect(destination)

        # Avoid duplicate attendance before relying on the database constraint
        existing = db.session.get(Attendance, (user_id, event_id))
        if existing is not None:
            db.session.rollback()
            flash("You are already attending this event.", "info")
            return redirect(destination)

        # Count registrations while the event capacity decision remains locked
        attendee_count = db.session.scalar(
            select(func.count()).select_from(Attendance).where(
                Attendance.event_id == event_id
            )
        )
        # Treat missing capacity as unlimited and reject full or overfull events
        if event.capacity is not None and attendee_count >= event.capacity:
            db.session.rollback()
            flash("This event is full.", "warning")
            return redirect(destination)

        db.session.add(Attendance(user_id=user_id, event_id=event_id))
        db.session.commit()
    except IntegrityError:
        # Handle a duplicate that reaches the composite primary-key constraint
        db.session.rollback()
        flash("You are already attending this event.", "info")
        return redirect(destination)
    except OperationalError:
        # Release failed locks or transactions before allowing a safe retry
        db.session.rollback()
        flash("Attendance is busy. Please try again.", "error")
        return redirect(destination)
    except SQLAlchemyError:
        # Keep the session usable after any other attendance database failure
        db.session.rollback()
        flash("Attendance could not be saved. Please try again.", "error")
        return redirect(destination)

    flash("You are now attending this event.", "success")
    return redirect(destination)


@events.route("/events/<int:event_id>/leave", methods=["POST"])
@login_required
def leave_event(event_id):
    # Retrieve the selected event or return a 404 error if it does not exist
    event = db.get_or_404(Event, event_id)
    destination = url_for("events.event_details", event_id=event_id)

    # Preserve private-event authorization for state-changing requests
    if event.privacy != "Public" and event.organiser_id != g.user.user_id:
        abort(403)

    attendance = db.session.get(Attendance, (g.user.user_id, event_id))
    if attendance is None:
        flash("You are not registered for this event.", "info")
        return redirect(destination)

    try:
        db.session.delete(attendance)
        db.session.commit()
    except SQLAlchemyError:
        # Restore the session after a failed attendance deletion
        db.session.rollback()
        flash("Your registration could not be removed. Please try again.", "error")
        return redirect(destination)

    flash("You are no longer attending this event.", "success")
    return redirect(destination)


@events.route("/my-attending-events")
@login_required
def my_attending_events():
    # Preserve existing bookmarks while keeping one attendance-page query
    return redirect(url_for("events.my_events"))


@events.route("/events/create", methods=["GET", "POST"])
@login_required
def create_event():

    # Create the event creation form
    form = CreateEventForm()

    # Retrieve all available event categories
    categories = (
        Category.query
        .order_by(Category.name)
        .all()
    )

    # Create a new event when the submitted information is valid
    if form.validate_on_submit():

        # Normalize category identifiers before using them in database records
        try:
            selected_category_ids = {
                int(category_id)
                for category_id in request.form.getlist("categories")
            }
        except ValueError:
            flash("One or more selected categories are invalid.", "error")
            return render_template(
                "create_event.html",
                form=form,
                categories=categories,
            )

        # Reject submitted identifiers that are not present in the database
        valid_category_ids = {
            category.category_id
            for category in categories
            if category.category_id in selected_category_ids
        }
        if valid_category_ids != selected_category_ids:
            flash("One or more selected categories are invalid.", "error")
            return render_template(
                "create_event.html",
                form=form,
                categories=categories,
            )

        event = Event(

            # Store the event's basic details
            title=form.title.data,
            description=form.description.data,

            # Store the event's location information
            venue_name=form.venue_name.data,
            address=form.address.data,
            city=form.city.data,
            country=form.country.data,
            location_notes=form.location_notes.data,

            # Store when the event will take place
            start_datetime=form.start_datetime.data,
            end_datetime=form.end_datetime.data,

            # Store additional event information if provided
            capacity=form.capacity.data,
            latitude=form.latitude.data,
            longitude=form.longitude.data,

            # Store the event visibility
            privacy=form.privacy.data,

            # Associate the event with the logged in organiser
            organiser_id=g.user.user_id

        )

        try:
            # Save the event and category associations in one transaction
            db.session.add(event)
            db.session.flush()

            for category_id in valid_category_ids:
                db.session.add(
                    EventCategory(
                        event_id=event.event_id,
                        category_id=category_id,
                    )
                )

            db.session.commit()
        except SQLAlchemyError:
            # Restore the session after a failed event-creation transaction
            db.session.rollback()
            flash("The event could not be created. Please try again.", "error")
            return render_template(
                "create_event.html",
                form=form,
                categories=categories,
            )

        flash("Event created successfully!")

        return redirect(
            url_for("events.manage_events")
        )

    # Display the event creation form
    return render_template(
        "create_event.html",
        form=form,
        categories=categories
    )
