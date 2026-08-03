from flask import (
    Blueprint,
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


@events.route("/my-events")
@login_required
def my_events():
    # Retrieve organised events and their categories without repeated queries
    organiser_events = db.session.scalars(
        select(Event)
        .where(Event.organiser_id == g.user.user_id)
        .options(selectinload(Event.categories))
        .order_by(Event.start_datetime)
    ).all()

    # Display the organiser's events page
    return render_template(
        "my_events.html",
        events=organiser_events
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
    cities = (
        db.session.query(Event.city)
        .filter_by(privacy="Public")
        .distinct()
        .order_by(Event.city)
        .all()
    )

    # Start with all public events
    query = (
        Event.query
        .filter_by(privacy="Public")
        .options(selectinload(Event.categories))
    )

    # Filter events whose titles contain the search term
    if search:

        query = query.filter(
            Event.title.ilike(f"%{search}%")
        )

    # Filter events by category
    if category_id:

        query = query.join(EventCategory).filter(
            EventCategory.category_id == category_id
        )

    # Filter events by city
    if selected_city:

        query = query.filter(
            Event.city == selected_city
        )

    # Retrieve the matching events ordered by their start date
    public_events = (
        query
        .order_by(Event.start_datetime)
        .all()
    )

    # Display the public events page
    return render_template(
        "browse_events.html",
        events=public_events,
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
    # Retrieve the current user's registrations and card categories efficiently
    attending_events = db.session.scalars(
        select(Event)
        .join(Attendance)
        .where(Attendance.user_id == g.user.user_id)
        .options(selectinload(Event.categories))
        .order_by(Event.start_datetime)
    ).all()

    return render_template(
        "my_attending_events.html",
        events=attending_events,
    )


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
            url_for("events.my_events")
        )

    # Display the event creation form
    return render_template(
        "create_event.html",
        form=form,
        categories=categories
    )
