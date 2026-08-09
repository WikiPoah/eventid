from functools import wraps

from flask import flash, g, redirect, request, session, url_for

LOGIN_MESSAGES = {
    "events.my_events": "Please log in to view your events.",
    "events.manage_events": "Please log in to manage events.",
    "events.create_event": "Please log in to create an event.",
}


# Restrict access to routes that require a logged in user
def login_required(view):

    @wraps(view)
    def wrapped_view(*args, **kwargs):

        # Clear stale sessions and redirect users who are not authenticated
        if "user_id" not in session or g.user is None:

            session.pop("user_id", None)

            message = LOGIN_MESSAGES.get(
                request.endpoint,
                "Please log in to continue.",
            )
            flash(message, "info")
            destination = request.full_path.rstrip("?")
            return redirect(url_for("auth.login", next=destination))

        return view(*args, **kwargs)

    return wrapped_view
