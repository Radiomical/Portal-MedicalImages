# Portal Medical Images

A Django portal for educational imaging cases and image-series browsing.

## Development status

The `next` line is an isolated refactor. It is not a production replacement yet.
The application targets Python 3.13.17 and Django 6.1.3. Dependencies and hashes
are locked in `requirements.txt`. Deployment still requires an isolated staging environment and a database/media
backup and restore rehearsal.

## Local checks

```sh
python3.13 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements.txt
.venv/bin/python manage.py check --settings=portal.settings_test
.venv/bin/python manage.py test tests --settings=portal.settings_test --noinput
./scripts/secret-scan.sh
```

Tests use synthetic accounts, an in-memory SQLite database and an in-memory mail
backend. No production database or email service is contacted. CI also runs the same tests against an ephemeral PostgreSQL database. This does not prove
compatibility with an existing deployed schema.

## Container

```sh
docker build -t portal:0.1.0-dev .
```

The image runs as UID 10001 and starts Gunicorn on port 8081. Startup does not run
migrations, import data or modify the production instance. Configure a separate
database, media volume and environment for each staging instance. Restrict the
host port to loopback when a local reverse proxy or tunnel is used.

The image includes WhiteNoise for collected static assets. Recover the original
CSS, JavaScript and branding into `static-src` before claiming visual parity.
Collect assets into a dedicated `STATIC_ROOT` volume before starting the server.
Patient images must never be copied into the source tree or container image.

## Configuration

Supply configuration through the process environment or a private container
`--env-file`. Do not commit a filled environment file.

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Required deployment secret, separate for isolated staging |
| `DEBUG` | Explicit boolean, false by default |
| `ALLOWED_HOSTS` | Comma-separated hostname allowlist |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated HTTPS origins |
| `DB_ENGINE` | `postgresql` by default, `sqlite` only for isolated development |
| `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD` | Separate PostgreSQL database credentials |
| `DATABASE_HOST`, `DATABASE_PORT` | PostgreSQL connection, port 5432 by default |
| `DATABASE_SSLMODE` | PostgreSQL TLS mode, `require` by default |
| `MEDIA_ROOT`, `STATIC_ROOT` | Separate filesystem locations |
| `EMAIL_BACKEND` | Console by default. Configure an approved backend for live mail |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP settings when using that backend |
| `DEFAULT_FROM_EMAIL` | Deployment mail identity |
| `SECURE_COOKIES` | True by default |
| `SECURE_SSL_REDIRECT` | True by default |
| `TRUST_PROXY_HTTPS` | False by default. Enable only behind a trusted proxy which replaces the forwarded-proto header |
| `MAX_UPLOAD_FILES` | Optional request file-count limit. Unset preserves inherited unlimited count; production upload limits still need workload validation |

The historical `users` migration chain (0001 through 0042) and application static
assets have been recovered from the deployed source checkout. Tests now apply the
real migration chain to empty, isolated databases rather than synchronizing
synthetic tables. Do not fake migrations or apply a production baseline blindly.
Compare the actual schema and migration records first, back up database and media
consistently, and rehearse restoration before any schema transition.

## Privacy boundary

The inherited upload path can retain original DICOM files without applying a
metadata anonymization policy. JPEG conversion alone does not remove identifying
text burned into pixels. Existing behavior must not be treated as a guarantee of
anonymization. Original DICOM access, image validation and research consent need
separate verification before publication or reuse of real cases.

## Changelog

### 0.1.0 development

- Upgrade the Python and Django runtime and lock dependencies with hashes.
- Replace placeholder configuration with explicit environment settings.
- Parse boolean flags without treating the text `False` as true.
- Remove the obsolete Django six compatibility import.
- Preserve HTTP 401 status in API error responses.
- Handle case authors without a profile.
- Make inherited DICOM conversion use the configured media directory.
- Add synthetic regression tests, container definition and CI checks.
