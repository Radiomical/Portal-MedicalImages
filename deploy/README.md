# Portable deployment

The Dockerfile builds only the portal application, dependencies and static
sources. PostgreSQL, uploaded objects, credentials and tunnel tokens are not
part of the image. Configuration is supplied at runtime, never as build args.

Two Compose projects are provided:

| Mode | Services | Data | Inbound exposure |
| --- | --- | --- | --- |
| `compose.staging.yml` | web, PostgreSQL 18.6 | synthetic database and media volumes | web on host loopback port 8081 only |
| `compose.production.yml` | web, official cloudflared | existing external Azure PostgreSQL and R2 | no published container ports |

Production has no Nginx dependency. WhiteNoise serves collected static files.
The connector reaches `http://web:8081` on the private application network.
Both containers also need outbound connectivity: web to Azure/R2/SMTP and
cloudflared to Cloudflare. The application network is internal, with separate
egress networks; `internal: true` alone would prevent required external access.
No Docker socket, host networking, privileged mode or production media volume
is needed. The image is nonroot, read-only and capability-free at runtime.
The Compose healthcheck checks a local socket only, not database health.

## Prerequisites and private configuration

Docker Engine and Compose v2 must be available on the target Linux VM. Network
policy must allow required outbound traffic, including Cloudflare Tunnel port
7844 (UDP for QUIC or TCP for HTTP/2), Azure PostgreSQL, HTTPS R2 and SMTP 587.
No inbound web firewall opening is needed. SSH/management policy is separate.
Azure firewall/network access must permit the new VM. Database connectivity,
certificate validation, R2 bucket ownership/policies, sending-domain validation
and Access/rate-limit policies must be checked before any production move.

`.env.example` is a complete variable-name reference with empty assignments,
not a ready-to-run configuration. Only applicable settings belong in each
private file; empty boolean/integer fields are not substitutes for values.
Three separate production files avoid disclosing the tunnel token to web or
application credentials to the connector:

1. A Compose selection file sets `PORTAL_IMAGE` to an explicit tested image tag
   or digest, `PORTAL_PRODUCTION_ENV_FILE` and `PORTAL_TUNNEL_ENV_FILE` to absolute
   private paths, and `PORTAL_DATABASE_CA_FILE` to a readable PostgreSQL CA bundle
   obtained from the provider. The public CA file must be readable by container UID 65532 (for example, mode 0644); the private credential files remain 0600. `latest` and unversioned image names must not be used.
2. The application file sets `SECRET_KEY`, `DEBUG=false`, exact `ALLOWED_HOSTS`,
   HTTPS `CSRF_TRUSTED_ORIGINS`, a validated `ADMIN_URL_PATH`, PostgreSQL host,
   port, database, user and password, R2 endpoint/credentials and distinct image
   and private DICOM buckets, and transactional-mail settings. Compose enforces
   PostgreSQL `verify-full`, R2 storage, secure cookies, HTTPS redirect and
   trusted proxy HTTPS. The CA bundle is mounted read-only at
   `/run/certs/database-ca.pem`; Compose points `DATABASE_SSLROOTCERT` there.
   The CA bundle is public certificate material, not the database password.
3. The connector file contains only `TUNNEL_TOKEN`, obtained securely from the
   remotely-managed tunnel's installation flow. The official image reads it
   from the environment; it is not interpolated into command arguments.

Every private file must be outside the checkout, owned by the operator and mode
`0600` in a restricted directory. Operators can use `umask 077` before creating
files and `chmod 600` afterwards. Secrets must not be pasted into tickets, chat,
command lines, logs or Git. `docker compose config` without `--quiet`, Docker
inspection and environment dumps can reveal secrets; never publish their
output. Docker daemon access remains equivalent to privileged host access.

Storage choices must be explicit: public JPEG delivery requires
`R2_IMAGE_PUBLIC_BASE_URL` and the image bucket's public custom-domain policy.
Leaving the origin unset uses private signed image URLs. DICOM remains separate
and private in either case. `DICOM_RETENTION_ENABLED`, upload limits and
`CASE_MEDIA_DUAL_WRITE`/`CASE_MEDIA_NORMALIZED_READ` must match the approved data
plan; normalized reads must not be enabled before reconciliation. Optional
`MAX_UPLOAD_FILES` can be omitted to retain the inherited file-count behavior.
For Resend, set `EMAIL_PROVIDER=resend`, a verified `DEFAULT_FROM_EMAIL` and
`EMAIL_HOST_PASSWORD`; host, username, port and STARTTLS are pinned by the
application. An empty `DEFAULT_REPLY_TO_EMAIL` omits Reply-To. No test email is
sent automatically.

## Build and synthetic preview on a new VM

An immutable release or commit is selected first. From that checkout:

```sh
docker build --tag portal-medicalimages:0.1.0-portable-preview .
```

A private preview file sets `DATABASE_PASSWORD`, `SECRET_KEY`,
`DB_ENGINE=postgresql`, `ALLOWED_HOSTS` to the intended preview hostname plus
local test hosts, and appropriate HTTPS/cookie settings. Export its absolute
path as `PORTAL_STAGING_ENV_FILE`, and supply the same file to `--env-file`.
The default preview uses filesystem media and a dummy mail backend. It must
never contain production credentials or connect to the production database.

```sh
docker compose --env-file "$PORTAL_STAGING_ENV_FILE" -f deploy/compose.staging.yml config --quiet
docker compose --env-file "$PORTAL_STAGING_ENV_FILE" -f deploy/compose.staging.yml up -d db
docker compose --env-file "$PORTAL_STAGING_ENV_FILE" -f deploy/compose.staging.yml -f deploy/compose.setup.yml run --rm --no-deps web manage.py migrate --noinput
docker compose --env-file "$PORTAL_STAGING_ENV_FILE" -f deploy/compose.staging.yml -f deploy/compose.setup.yml run --rm --no-deps web manage.py collectstatic --noinput
docker compose --env-file "$PORTAL_STAGING_ENV_FILE" -f deploy/compose.staging.yml -f deploy/compose.setup.yml run --rm --no-deps web manage.py seed_preview
docker compose --env-file "$PORTAL_STAGING_ENV_FILE" -f deploy/compose.staging.yml up -d web
```

Seeding refuses an existing database rather than overwriting it. The setup
file is an explicit one-off override, not a permanently writable web service.
The preview blocks mutations and private/admin routes and is not an
authenticated-workflow test environment. Its loopback port is not public; a
separate authorized test tunnel may expose synthetic fixtures if needed.
The fixed preview tag is a local build label, not a published release claim.

## Prepare production without connecting a tunnel

A tested artifact may be loaded from the audited CI archive after checksum and
image-ID validation. Alternatively, an explicit image tag can be built from the
selected commit and must pass the same validation before it is approved.
Set `PORTAL_IMAGE` in the private selection file to that exact image, not the
preview label. The following shell variable names only a private file path:

```sh
export PORTAL_COMPOSE_ENV_FILE=/absolute/private/path/compose.env
docker compose --env-file "$PORTAL_COMPOSE_ENV_FILE" -f deploy/compose.production.yml config --quiet
docker compose --env-file "$PORTAL_COMPOSE_ENV_FILE" -f deploy/compose.production.yml -f deploy/compose.production.setup.yml run --rm --no-deps web manage.py collectstatic --noinput
docker compose --env-file "$PORTAL_COMPOSE_ENV_FILE" -f deploy/compose.production.yml up -d web
```

Initialization does not run production migrations, seed data or start the
connector. Database schema changes require a consistent backup, restore and
rollback plan and a separate approved migration step. The static volume must
contain assets from the selected image before web starts. During updates a
new project/static volume is preferred, so a previous container's static tree
remains available for rollback. Do not mutate an active image's collected
static directory in place. Uploaded media is not included in the static volume.

Before activation, validate the origin internally from the application network
with the intended `Host` and `X-Forwarded-Proto: https`: home/case 200, no redirect
loop, CSRF-protected login form, versioned static files and security headers.
A request with `X-Forwarded-Proto: http` must redirect to HTTPS. Forwarded HTTPS
is trusted only because no untrusted client can directly reach the origin:
only cloudflared and explicitly trusted containers may join this network.
Django's CSRF trusted origins do not authorize an arbitrary proxy.

## Cloudflare routing and activation

The remotely-managed tunnel must route the selected public hostname to
`http://web:8081`. The HTTP Host header must remain the real allowed public
hostname, or be overridden explicitly to it in the tunnel's origin settings.
Cloudflare's public HTTPS scheme must reach Django as `X-Forwarded-Proto`.
`SECURE_PROXY_SSL_HEADER` is enabled by `TRUST_PROXY_HTTPS`; synthetic direct
origin tests verify Django behavior, but they do not prove a particular account's
edge policy. An authorized isolated tunnel must confirm the actual edge headers,
CSRF, redirect and Access behavior before a live route is moved. Header absence
or a redirect loop is a stop condition, not a reason to disable HTTPS/CSRF.

After approval and route validation only:

```sh
docker compose --env-file "$PORTAL_COMPOSE_ENV_FILE" -f deploy/compose.production.yml up -d cloudflared
```

Access must cover the configured administrative root and descendants. Changing
the Django route alone does not configure Access. Public cases/JPEG and
account-login rate limiting need their own policies. The connector runs at
normal info logging; debug logging can include request headers and must not be
used with sensitive traffic. Nginx-specific rules are not silently carried over:
legacy admin aliases must remain unrouted, original DICOM must never be served
by a public origin, and any prior upload/body-size/timeouts must be compared with
Django and Gunicorn limits. WhiteNoise and application middleware supply static
and response-security headers, not Cloudflare Access itself.

## Two connectors and migration without an avoidable outage

Cloudflare supports multiple replicas of the same tunnel. They share remote
configuration and can both receive live traffic immediately; they are not a
staging/primary pair, and traffic is not guaranteed to stay on one replica.
Both must resolve every relevant hostname route and serve compatible data,
static files, secrets/session keys and application versions before coexistence.

In particular, a remote origin of `http://localhost:8080` on the old host does
not become `http://web:8081` only for the new connector. A Docker connector's
localhost is its own container. Starting the new replica with an incompatible
shared origin can cause intermittent failures. A tunnel can also carry other
services, such as SSH or a preview: every such route must remain reachable from
every active replica. This web-only Compose does not automatically recreate
those other routes.

A safe move uses these gates:

1. Prove the new stack on a separate synthetic test tunnel or an isolated origin
   check. Do not attach the live token merely to test a new container.
2. Inventory all existing routes and plan a common reachable origin naming
   scheme for both old and new connectors, including non-web routes. Establish
   destination compatibility before changing the shared tunnel configuration.
3. Back up and reconcile the external data and storage configuration. Both web
   instances must tolerate simultaneous traffic and shared sessions. The new
   host may not have needed local originals or maintenance resources.
4. Only after approval, activate the additional connector, verify each replica
   independently and observe healthy edge requests. Access and rate-limit
   policy must remain attached to the intended public hostname/path.
5. Stop the old connector only after validation, retaining its configuration and
   rollback route. Do not delete the old host, data or token as part of this step.

No live tunnel route, connector or host is changed by adding these files.
Production activation and Nginx removal remain operational steps, not an effect
of merging a PR. A staged compatibility plan or separate temporary tunnel may
be needed; replicas alone do not guarantee a zero-downtime migration.

## Rollback and limits

Stop only the new connector/Compose project if validation fails. Retain the
previous image, static volume and approved route configuration. Once writes
have occurred, database rollback requires reconciliation; blindly restoring an
older dump can lose new data. Do not use host-wide prune or `down -v` for a
production rollback. Existing backups, originals and unrelated containers are
not cleanup targets.

Official references:
- https://developers.cloudflare.com/tunnel/configuration/
- https://developers.cloudflare.com/tunnel/reference/run-parameters/
- https://developers.cloudflare.com/tunnel/reference/origin-parameters/
- https://hub.docker.com/r/cloudflare/cloudflared/tags
