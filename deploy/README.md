# Synthetic staging

This Compose definition is for a public, read-only preview containing only
synthetic fixtures. Never mount production media, copy production environment
files, or connect it to the production database. It has its own internal network,
database and static/media volumes. Only web port 8081 binds to host loopback.

Supply `DATABASE_PASSWORD`, `SECRET_KEY`, `DB_ENGINE=postgresql`, secure cookie
settings and `TRUST_PROXY_HTTPS=true` in a private environment file outside the
source tree. Export `PORTAL_STAGING_ENV_FILE` with that file's absolute path and
provide the same file to Compose's `--env-file`. Do not print resolved Compose
configuration because it includes secrets.

Before starting web, build the explicit image, start db, run migrations, collect
static assets and seed synthetic data using one-off jobs with writable staging
volumes. Web mounts static and media read-only. The preview blocks mutation
requests, account creation, reset, admin, profiles and API endpoints and disables
mail. Synthetic authors should have unusable passwords. It is not an authenticated
workflow test environment.

The tunnel route is HTTP `http://localhost:8081`. Production is not part of this
Compose project. Do not replace the existing production Gunicorn/Nginx services.

## Rollback

Run `docker compose --env-file PRIVATE_ENV -f deploy/compose.staging.yml down` to
stop only this project; remove the preview hostname route separately. Add `-v`
only to erase this project's synthetic volumes. Never use a host-wide prune.
To roll back the Docker installation itself, after stopping this project's
containers, remove docker-ce, docker-ce-cli, containerd.io, docker-buildx-plugin
and docker-compose-plugin, then remove the Docker apt source and key. Do not
remove other services, data directories or firewall rules indiscriminately.

## Explicit initialization

After exporting `PORTAL_STAGING_ENV_FILE`:

```sh
docker compose --env-file "$PORTAL_STAGING_ENV_FILE" -f deploy/compose.staging.yml build web
docker compose --env-file "$PORTAL_STAGING_ENV_FILE" -f deploy/compose.staging.yml up -d db
docker compose --env-file "$PORTAL_STAGING_ENV_FILE" -f deploy/compose.staging.yml -f deploy/compose.setup.yml run --rm --no-deps web sh -c 'python manage.py migrate --noinput && python manage.py collectstatic --noinput && python manage.py seed_preview'
docker compose --env-file "$PORTAL_STAGING_ENV_FILE" -f deploy/compose.staging.yml up -d web
```

The setup override makes only this job's synthetic volumes writable. `run` does
not publish the web service port by default. Do not repeat seed on an existing
database; the command refuses rather than replacing any data. The web container
uses the unmodified read-only staging definition after initialization.
