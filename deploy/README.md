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

## Planned managed database and object storage transition

The optional `MEDIA_STORAGE=r2` backend is preparation only. Keep filesystem
storage enabled until resource ownership, EU jurisdiction, private-bucket status,
CORS, credentials and a synthetic end-to-end test have been verified. Only the
backend receives `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
`R2_IMAGE_BUCKET`, `R2_DICOM_BUCKET` and `R2_SIGNED_URL_SECONDS` (default 300).
R2 URLs are short-lived bearer links using its S3 endpoint, not a custom domain.
Do not log those URLs or put them into persistent database fields.

The image backend signs only display-image keys. It does not authenticate a
viewer: case-level permissions must be checked before rendering any image URL.
The current public case pages remain public; private cases need a separate
permission workflow. Signed URLs do not make a public page private. The planned
viewer must renew expired URLs rather than saving them permanently.

Original DICOM retention is an explicit, separate operation to a distinct private
bucket. No URL or download route is provided for that bucket. Do not connect the
legacy DICOM upload pipeline to R2 yet: it still uses local conversion paths and
requires a storage-aware upload refactor, policy checks and synthetic integration
tests. Raw originals remain quarantined until metadata and pixel review.

For Supabase, retain Django authentication initially. Use a dedicated database
role and TLS, restrict or disable the Data API for application tables, and verify
the target PostgreSQL version before planning restore from PostgreSQL 18.
The target project and buckets are owner-created. No actual migration is part of
this configuration. Preserve the old database/media during a future approved
cutover and rehearse a rollback that accounts for writes made after the switch.

Object writes use atomic `PutObject(IfNoneMatch="*")` and fail on a key collision, including quarantine originals. They never overwrite or delete an existing object. Reconcile uncertain outcomes before retrying. This is create-only protection, not immutable retention against other credentials, lifecycle rules or dashboard changes. R2 support: https://developers.cloudflare.com/r2/api/s3/extensions/

## Storage-aware uploads and original retention

New upload keys use random UUIDs, not usernames or source filenames. The service
pre-decodes the whole submission before saving a case. JPEGs are re-encoded (EXIF
is not carried over); DICOM is limited to single-frame grayscale and retains the
inherited educational grayscale conversion. This is not diagnostic windowing or
an anonymization guarantee. Text burned into pixels still needs review.

Both create and edit use the same storage API and a database transaction. Failed
edits keep existing case fields and image references. External object writes are
not transactional: an uncertain or partial failure may leave unreferenced new
objects, which must be reconciled by manifest and hash, not blindly deleted or
retried. Existing objects are never overwritten or automatically deleted.

Original retention requires `DICOM_RETENTION_ENABLED=true`; a submission asking
to retain originals fails explicitly when disabled. It never silently drops an
original requested for retention. With R2, originals use the separate quarantine
bucket with no URL generation. Without R2, originals go to `PRIVATE_DICOM_ROOT`
(default `.local/private-dicom`) with restrictive permissions, outside public
`MEDIA_ROOT`. Never expose that directory through a web server. A database-only
`OriginalDicom` manifest records the private key, SHA256 and byte size. No original
filename is stored. Cases with retained originals cannot be deleted until an
explicit retention workflow deals with them. Existing local DICOM is not moved by
this change. Retention is not enabled in public staging.

Upload bounds default to 32 MiB/file, 256 MiB/case and 40 million pixels/image;
configure `MAX_IMAGE_UPLOAD_BYTES`, `MAX_CASE_UPLOAD_BYTES`, `MAX_IMAGE_PIXELS`.
Production activation needs capacity testing and an agreed upload policy.
For Supabase, set `DATABASE_SSLMODE=verify-full` and `DATABASE_SSLROOTCERT` to the
owner-supplied CA path. Verify both client-to-pooler and pooler-to-database TLS.
