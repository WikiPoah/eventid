# Testing and quality

The suite covers authentication, authorization, event lifecycle, discovery, pagination, concurrency-safe attendance, images, exports, errors, demo seeding, UI contracts, health, configuration, and security headers.

Run `python -m pytest` for behavior and `python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=85` for coverage. The 85% floor sits below the measured baseline of 88% while remaining high enough to catch material regressions. Migrations are excluded because Alembic behavior is validated operationally through downgrade, upgrade, current, and drift checks.

Black formats Python with an 88-character line length. Ruff checks errors, imports, common bugs, and pyflakes. CI uses the exact pinned development dependencies and Python 3.12.

Before release, also verify app import, route enumeration, migration downgrade/upgrade on a disposable database, demo seed twice, production WSGI startup, `/health`, browser layouts, keyboard focus, reduced motion, ignored files, and a clean diff.
