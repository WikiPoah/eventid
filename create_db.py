from flask import Flask

from app.database.db import db
from app.models import User


app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///eventid.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


with app.app_context():

    db.create_all()

    print("Database created successfully!")