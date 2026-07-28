from app.database.db import db


# Store the available categories that can be assigned to events
class Category(db.Model):

    __tablename__ = "categories"

    # Uniquely identify each category
    category_id = db.Column(db.Integer, primary_key=True)

    # Store the category's name
    name = db.Column(db.String(50), unique=True, nullable=False)

    # Link each category to the events assigned to it
    events = db.relationship(
        "EventCategory",
        back_populates="category",
        cascade="all, delete-orphan"
    )

    def __repr__(self):

        # Return a readable representation of the category object
        return f"<Category {self.name}>"