from app.database.db import db
from app.models.category import Category


# Define the default event categories available in the application
EVENT_CATEGORIES = [
    "Arts & Culture",
    "Community & Charity",
    "Education & STEM",
    "Food & Drink",
    "Music",
    "Networking",
    "Socialising",
    "Sports & Fitness",
    "Technology",
]


def seed_categories():

    # Insert each predefined category if it doesn't already exist
    for category_name in EVENT_CATEGORIES:

        existing_category = Category.query.filter_by(
            name=category_name
        ).first()

        if existing_category is None:

            db.session.add(
                Category(name=category_name)
            )

    # Save any newly added categories to the database
    db.session.commit()