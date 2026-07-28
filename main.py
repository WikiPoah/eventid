from flask import Flask, render_template, session, g

from app.database.db import db
from app.routes.auth import auth
from app.routes.events import events
from app.models.user import User

app = Flask(
    __name__,
    template_folder="app/templates",
    static_folder="app/static"
)

# Configure the application's security and database settings
app.config["SECRET_KEY"] = "change-this-to-a-random-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///eventid.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Connect the database to the Flask application
db.init_app(app)

# Register the application's route blueprints
app.register_blueprint(auth)
app.register_blueprint(events)


@app.before_request
def load_logged_in_user():

    # Load the currently logged in user before each request
    g.user = None

    if "user_id" in session:

        g.user = User.query.get(session["user_id"])


# Display the homepage when users
# visit the website
@app.route("/")
def home():

    # Pass the logged in user's information to the homepage
    user = None

    if "user_id" in session:

        user = User.query.get(session["user_id"])

    return render_template("index.html", user=user)


if __name__ == "__main__":

    # Start the Flask development server
    app.run(debug=True)