from flask import (
    Blueprint,
    render_template,
    g,
    flash,
    redirect,
    url_for,
    abort
)

from app.decorators import login_required

from app.forms.event_forms import CreateEventForm
from app.database.db import db
from app.models.event import Event

events = Blueprint("events", __name__)


@events.route("/my-events")
@login_required
def my_events():

    # Retrieve the currently logged in user's information
    user = g.user

    # Retrieve all events organised by the current user
    organiser_events = user.events

    # Display the organiser's events page
    return render_template(
        "my_events.html",
        events=organiser_events
    )


@events.route("/events")
@login_required
def browse_events():

    # Retrieve all public events ordered by their start date
    public_events = (
        Event.query
        .filter_by(privacy="Public")
        .order_by(Event.start_datetime)
        .all()
    )

    # Display the public events page
    return render_template(
        "browse_events.html",
        events=public_events
    )


@events.route("/events/<int:event_id>")
@login_required
def event_details(event_id):

    # Retrieve the selected event or return a 404 error if it does not exist
    event = Event.query.get_or_404(event_id)

    # Prevent users from viewing private events they do not organise
    if (
        event.organiser_id != g.user.user_id
        and event.privacy != "Public"
    ):

        abort(403)

    # Display the selected event's details
    return render_template(
        "event_details.html",
        event=event
    )


@events.route("/events/create", methods=["GET", "POST"])
@login_required
def create_event():

    # Create the event creation form
    form = CreateEventForm()

    # Create a new event when the submitted information is valid
    if form.validate_on_submit():

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

            # Associate the event with the logged in organiser
            organiser_id=g.user.user_id

        )

        # Save the new event to the database
        db.session.add(event)
        db.session.commit()

        flash("Event created successfully!")

        return redirect(
            url_for("events.my_events")
        )

    # Display the event creation form
    return render_template(
        "create_event.html",
        form=form
    )