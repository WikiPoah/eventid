from flask import Flask, render_template
from app.database.db import db

app = Flask(
    __name__,
    template_folder="app/templates",
    static_folder="app/static"
)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///eventid.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


# Display the homepage when users
# visit the website
@app.route("/")
def home():

    return render_template("index.html")


if __name__ == "__main__":

    app.run(debug=True)