# Production deployment and recovery

## Selected platform

Render is the reference deployment because its Blueprint supports a Python web service, managed PostgreSQL, pre-deploy migration command, environment secrets, persistent disk, health checks, and GitHub-based main-branch deployment in one reviewable file.

## Deploy

1. In Render, create a Blueprint from this GitHub repository and select `render.yaml`.
2. Review region and paid `starter` web, database, and disk plans before creation.
3. Confirm `main` is the deployment branch and keep the generated `SECRET_KEY` secret.
4. Replace `RATELIMIT_STORAGE_URI=memory://` with a private Redis URL before scaling beyond one process/instance.
5. Deploy; Render installs runtime packages, runs `flask --app main:app db upgrade`, starts Waitress, and checks `/health`.

`DATABASE_URL` accepts `postgres://` and `postgresql://` provider formats and normalizes them for psycopg 3. Secure cookies and proxy handling are enabled by `FLASK_ENV=production`.

## Images

The blueprint mounts `/var/data/eventid`; uploads live below it and survive deploys. A single instance can use this disk. Render disks do not provide shared multi-instance storage, so horizontal scaling requires adapting the image backend to S3-compatible object storage. Back up the disk separately from PostgreSQL.

## Database backup and restore

Use Render PostgreSQL recovery/export features or `pg_dump` with a short-lived connection string. Before a risky migration, take a database backup and verify its timestamp. Restore into a separate database first, validate it, update `DATABASE_URL` during a maintenance window, then run `flask --app main:app db upgrade`. Never place connection strings in shell history, documentation, or Git.

For local SQLite, stop the app and copy `instance/eventid.db` plus `instance/event_images`. Restore both together, then run migrations. Preserve environment secrets independently; database backups do not contain the Flask secret.

Test downgrade/upgrade compatibility on a disposable copy, never directly on the only production database. The health endpoint reports only `{"status":"ok"}` or `{"status":"unhealthy"}`.
