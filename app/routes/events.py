from flask import Blueprint, render_template, g

from app.decorators import login_required

events = Blueprint("events", __name__)


@events.route("/my-events")
@login_required
def my_events():

    # Retrieve the currently logged in user's information
    user = g.user

    # Display the user's personal events page
    return f"<h1>{user.first_name}'s Events</h1>"