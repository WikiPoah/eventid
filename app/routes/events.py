import csv
from datetime import datetime
from io import StringIO

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
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

events = Blueprint("events", __name__)

NEARLY_FULL_THRESHOLD = 0.8
EVENT_STATUSES = {"Draft", "Published", "Cancelled"}


def _safe_csv_value(value):
    """Prevent attendee-controlled text from becoming a spreadsheet formula."""

    text_value = str(value)
    if text_value.startswith(("=", "+", "-", "@")):
        return f"'{text_value}"
    return text_value


def _owned_event_or_404(event_id):
    """Return an event owned by the current user or reject access."""

    event = db.get_or_404(Event, event_id)

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

    return event.privacy == "Public" or attendance is not None


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
            Event.status.in_(("Published", "Cancelled")),
        )
        .options(selectinload(Event.categories))
        .order_by(Event.start_datetime)
    ).all()

    return render_template(
        "my_events.html",
        events=attending_events,
    )


@events.route("/calendar")
@login_required
def calendar():
    """Show attended and organised events in one deduplicated schedule."""

    current_time = datetime.now()

    relevant_events = db.session.scalars(
        select(Event)
        .outerjoin(
            Attendance,
            (Attendance.event_id == Event.event_id)
            & (Attendance.user_id == g.user.user_id),
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
        .options(selectinload(Event.categories))
        .order_by(Event.start_datetime, Event.event_id)
    ).all()

    upcoming_events = [
        event for event in relevant_events if event.end_datetime >= current_time
    ]

    past_events = [
        event for event in relevant_events if event.end_datetime < current_time
    ]

    return render_template(
        "calendar.html",
        upcoming_events=upcoming_events,
        past_events=past_events,
    )


@events.route("/events")
def browse_events():

    # Retrieve the user's search and filter selections
    search = request.args.get("search", "").strip()

    # Retrieve the selected category
    category_id = request.args.get("category", type=int)

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
        .options(selectinload(Event.categories))
    )

    # Filter events whose titles contain the search term
    if search:
        statement = statement.where(Event.title.ilike(f"%{search}%"))

    # Filter events by category
    if category_id:
        statement = statement.join(EventCategory).where(
            EventCategory.category_id == category_id
        )

    # Filter events by city
    if selected_city:
        statement = statement.where(Event.city == selected_city)

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
        selected_city=selected_city,
    )


@events.route("/events/<int:event_id>")
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

    # Apply status and privacy authorization before rendering event data
    if not _can_view_event(event):
        abort(403)

    # Derive attendance controls from the eagerly loaded attendance records
    attendee_count = len(event.attendees)

    is_attending = g.user is not None and any(
        attendance.user_id == g.user.user_id for attendance in event.attendees
    )

    is_full = event.capacity is not None and attendee_count >= event.capacity

    return render_template(
        "event_details.html",
        event=event,
        attendee_count=attendee_count,
        is_attending=is_attending,
        is_full=is_full,
    )


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

    return response


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
        select(Event).where(Event.event_id == event_id).with_for_update()
    )


@events.route("/events/<int:event_id>/attend", methods=["POST"])
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

        # Prevent attendance registration for inaccessible private events
        if event.privacy != "Public" and event.organiser_id != user_id:

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
            .where(Attendance.event_id == event_id)
        )

        # Treat missing capacity as unlimited and reject full or overfull events
        if event.capacity is not None and attendee_count >= event.capacity:

            db.session.rollback()

            flash(
                "This event is full.",
                "warning",
            )

            return redirect(destination)

        db.session.add(
            Attendance(
                user_id=user_id,
                event_id=event_id,
            )
        )

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
        "You are now attending this event.",
        "success",
    )

    return redirect(destination)


@events.route("/events/<int:event_id>/leave", methods=["POST"])
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
                    latitude=form.latitude.data,
                    longitude=form.longitude.data,
                    privacy=form.privacy.data,
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
                .where(Attendance.event_id == event.event_id)
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

                        event.privacy = form.privacy.data

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


@events.route("/events/<int:event_id>/status", methods=["POST"])
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


@events.route("/events/<int:event_id>/delete-confirmation")
@login_required
def confirm_delete_event(event_id):

    event = _owned_event_or_404(event_id)

    return render_template(
        "delete_event.html",
        event=event,
    )


@events.route("/events/<int:event_id>/delete", methods=["POST"])
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
