from alembic.config import Config
from alembic.script import ScriptDirectory
from flask_migrate import check, upgrade
from sqlalchemy import inspect

from app.database.db import db
from main import create_app


def test_migrations_have_one_head_and_match_models(tmp_path):
    config = Config("migrations/alembic.ini")
    config.set_main_option("script_location", "migrations")
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1

    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "migration-test-only",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'migrations.db'}",
        }
    )
    with application.app_context():
        upgrade()
        upgrade()
        check()
        assert set(inspect(db.engine).get_table_names()) == (
            set(db.metadata.tables) | {"alembic_version"}
        )
        db.session.remove()
        db.engine.dispose()
