from functools import wraps

from flask import g, session, redirect, url_for


# Restrict access to routes that require a logged in user
def login_required(view):

    @wraps(view)
    def wrapped_view(*args, **kwargs):

        # Clear stale sessions and redirect users who are not authenticated
        if "user_id" not in session or g.user is None:

            session.pop("user_id", None)

            return redirect(url_for("auth.login"))

        return view(*args, **kwargs)

    return wrapped_view
