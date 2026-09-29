# Testing and quality

The suite covers authentication, authorization, event lifecycle, discovery, pagination, concurrency-safe attendance, images, exports, errors, demo seeding, UI contracts, health, configuration, and security headers.

Run `python -m pytest` for behavior and `python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=85` for coverage. The 85% floor is enforced by CI; the current coverage is reported by the command rather than assumed from an older baseline. Migrations are excluded because Alembic behavior is validated operationally through downgrade, upgrade, current, and drift checks.

Black formats Python with an 88-character line length. Ruff checks errors, imports, common bugs, and pyflakes. CI uses the exact pinned development dependencies and Python 3.12.

Before release, also verify app import, route enumeration, migration downgrade/upgrade on a disposable database, demo seed twice, production WSGI startup, `/health`, browser layouts, keyboard focus, reduced motion, ignored files, and a clean diff.

## Portfolio release verification

The final local baseline passed 186 tests with 89.20% application coverage,
Ruff, full Black checks, JavaScript syntax validation, parsing of all 26 Jinja
templates and Git whitespace checks. Local Python was 3.13; the CI workflow
targets Python 3.12. Six existing Alembic `get_engine` deprecation warnings
remain; they do not fail the migration/schema checks.

Browser verification used Chromium against a disposable seeded database with
real CSRF-protected forms. The attendee journey covered search, details, signup
return, registration, My Events, QR ticket, calendar, favourites and account
navigation. The organiser journey covered private event creation/editing,
invitation, pending request, approval, ticket availability and persisted check-in.
Mobile checks covered navigation, filter disclosure/keyboard access, long titles,
organiser controls, check-in and the horizontally scrolling month calendar.
No application runtime errors or first-party HTTP 5xx responses were observed.

These browser checks were run with an external temporary Playwright harness;
they are not a checked-in browser test suite or part of CI. PostgreSQL migration,
configuration and Waitress startup verification likewise used a disposable local
PostgreSQL 16 service; hosted Render acceptance remains a separate manual check.
