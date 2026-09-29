from app.database.db import db


class Category(db.Model):
    """A reusable event classification with stable database identity."""

    __tablename__ = "categories"

    category_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

    event_categories = db.relationship(
        "EventCategory", back_populates="category", cascade="all, delete-orphan"
    )

    # Provide read-only access to events without hiding association records
    events = db.relationship("Event", secondary="event_categories", viewonly=True)

    def __repr__(self):
        return f"<Category {self.name}>"
