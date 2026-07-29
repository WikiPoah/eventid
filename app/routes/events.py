from flask import (
    Blueprint,
    render_template,
    g,
    flash,
    redirect,
    url_for
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

    # Display the user's personal events page
    return f"<h1>{user.first_name}'s Events</h1>"


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