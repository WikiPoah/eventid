from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

# Create extension objects without binding them to a specific application
db = SQLAlchemy()
csrf = CSRFProtect()
