from flask import Flask

from app.database.db import db
from app.models import User


app = Flask(__name__)

# Configure the application's database settings
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///eventid.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Connect the database to the Flask application
db.init_app(app)


with app.app_context():

    # Create all database tables defined by the application models
    db.create_all()

    print("Database created successfully!")