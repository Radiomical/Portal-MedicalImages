# Configuration reference and migration checklist

This reference describes the supported runtime inputs, not their secret values.
`.env.example` is a blank name inventory, not a runnable file. Required values
must be supplied; optional integers should normally be omitted rather than left
blank. Production Compose overrides the settings explicitly listed in its
`environment` block, even when an env-file contains another value.

Secret values belong in a protected private file or a secret manager, never Git,
chat, screenshots, logs or a generated environment dump. A recovery plan uses an operator-controlled backup or a secure provider
replacement. It must not assume that a provider will show an old secret again. No credentials are created or rotated by this document.

## Compose selection (operator file, not application environment)
| Variable | Classification | Purpose / constraint | Source or recovery |
| --- | --- | --- | --- |
| `PORTAL_COMPOSE_ENV_FILE` | No | Shell path to the private Compose selection file; not read by Django or interpolated by Compose itself. | Operator chooses an absolute path outside the checkout. |
| `PORTAL_IMAGE` | No | Required immutable tested web tag or digest; never latest. | Build selected commit with Dockerfile or load the audited CI runtime archive; verify SHA256SUMS and Image ID. CI artifacts expire, so retain the approved archive or rebuild and revalidate. |
| `PORTAL_PRODUCTION_ENV_FILE` | Sensitive path | Required absolute path to private application configuration. | Operator creates mode 0600 outside Git; populate from the application rows below. |
| `PORTAL_STAGING_ENV_FILE` | Sensitive path | Private synthetic-preview configuration and Compose interpolation source. | Operator creates a separate mode-0600 file; never copy production credentials into preview. |
| `PORTAL_TUNNEL_ENV_FILE` | Sensitive path | Required private connector-only file containing TUNNEL_TOKEN. | Operator creates mode 0600, outside checkout; never give this file to web. |
| `PORTAL_DATABASE_CA_FILE` | No | Required host CA-bundle file mounted at /run/certs/database-ca.pem. | Obtain the CA chain from current Azure PostgreSQL TLS documentation or the approved OS trust bundle; readable by UID65532, e.g.0644. It is public certificate material. |

## Application identity and HTTPS
| Variable | Classification | Purpose / constraint | Source or recovery |
| --- | --- | --- | --- |
| `DJANGO_SETTINGS_MODULE` | No | Production portal.settings; preview portal.settings_staging. Selected by Compose. | Recipe selects it; never use test/staging settings with production data. |
| `SECRET_KEY` | Yes | Required Django signing key; no fallback. | Copy the existing key privately for a same-application migration. For a new installation generate a cryptographically random key into the private file/secret manager, never chat or command arguments. Rotation invalidates signed sessions/tokens and must be coordinated across replicas. |
| `DEBUG` | No | Production false (forced by Compose). | Deployment policy, not a provider credential. |
| `ALLOWED_HOSTS` | No | Comma-separated public hostnames plus explicitly needed local check hosts. Preview also requires its own hostname. | Chosen deployment DNS/tunnel hostnames; no scheme or wildcard. No fixed preview hostname is supplied by settings. |
| `CSRF_TRUSTED_ORIGINS` | No | Comma-separated exact HTTPS origins for browser form submissions. | Match the intended public scheme/host; not permission to trust arbitrary proxies. |
| `ADMIN_URL_PATH` | Sensitive configuration | Single non-reserved segment ending in slash; default xxx/. | Preserve existing deployment choice privately; match Access application root and descendants. This is not a password or authentication control. |
| `TRUST_PROXY_HTTPS` | No | Production true; trusts X-Forwarded-Proto from an unreachable-by-public origin. | Recipe/network design; validate actual connector header before activation. |
| `SECURE_COOKIES` | No | Production true for session and CSRF cookies. | Deployment policy; false only for isolated HTTP tests. |
| `SECURE_SSL_REDIRECT` | No | Production true; preview settings deliberately override to false on the loopback synthetic listener. | Deployment policy; do not disable to hide a tunnel redirect loop. |
| `SECURE_HSTS_SECONDS` | No | Default300, host-only; neither includeSubDomains nor preload. | Choose a reviewed policy; omit rather than leave an empty integer. |

## Database and libpq
| Variable | Classification | Purpose / constraint | Source or recovery |
| --- | --- | --- | --- |
| `DB_ENGINE` | No | postgresql in both Compose modes; sqlite only local/tests. | Recipe. |
| `DATABASE_HOST` | Sensitive identifier | External Azure PostgreSQL DNS name in production; Compose sets db in preview. | Azure portal: selected PostgreSQL flexible server Overview/connection details. Preserve DNS name for verify-full. |
| `DATABASE_PORT` | No | 5432 unless provider explicitly differs; preview forced5432. | Azure connection details. |
| `DATABASE_NAME` | Sensitive identifier | Existing database name; preview forced portal_staging. | Approved DB inventory/connection config or database administrator; server name is not the database name. |
| `DATABASE_USER` | Sensitive identifier | Application database role; preview forced portal_staging. | Existing private config/database administrator; use the approved least-privilege role, not a guessed server admin. |
| `DATABASE_PASSWORD` | Yes | Application DB role password; preview also supplies synthetic POSTGRES_PASSWORD via Compose. | Existing authorized private configuration/secret manager. If lost, DBA resets that exact role; Azure admin reset only resets the server administrator, not every app role. Update all dependents and test, never rotate just to migrate. |
| `DATABASE_SSLMODE` | No | Production verify-full forced; preview disable on isolated network. | Recipe. Hostname and trusted CA must both validate. |
| `DATABASE_SSLROOTCERT` | No | Container path to the CA file; production Compose forces /run/certs/database-ca.pem. | Mounted PORTAL_DATABASE_CA_FILE, not its host path. Existing deployment may use its OS CA bundle instead. |
| `DATABASE_CONN_MAX_AGE` | No | 0-60 seconds; omitted/empty defaults60, with health checks. | Operator selects for WSGI worker/DB capacity; set0 for ASGI unless using a supported pool. |
| `PGOPTIONS` | No, operationally sensitive | Optional libpq session options, not an application feature; a read-only rehearsal may use default_transaction_read_only=on. | Explicit maintenance/test procedure only. Omit in normal writable deployment; never copy a rehearsal guard without reviewing it. |
| `SSL_CERT_FILE` | No | Optional Python/OpenSSL trust-bundle path inherited by runtime; not the PostgreSQL sslrootcert selector. | Approved base-image/OS CA bundle. Preserve valid trust paths, not secrets; normally image-managed. |

## Storage and uploads
| Variable | Classification | Purpose / constraint | Source or recovery |
| --- | --- | --- | --- |
| `MEDIA_STORAGE` | No | Production r2; synthetic default filesystem. | Recipe. Switching backend alone does not copy files or remap DB keys. |
| `R2_ENDPOINT_URL` | Sensitive identifier | S3-compatible endpoint, including bucket jurisdiction. | Cloudflare R2 account details/S3 API endpoint; EU buckets require the EU endpoint, not a guessed global endpoint. |
| `R2_ACCESS_KEY_ID` | Credential identifier | S3 credential ID paired with the secret below, not a REST API bearer token. | Cloudflare R2 > Manage API tokens, approved object read/write scope for required buckets. Keep the pair in private configuration. |
| `R2_SECRET_ACCESS_KEY` | Yes | S3 credential secret; server-side only. | Shown once when creating an R2 token. If unavailable, create a scoped replacement and coordinate rotation; it cannot be displayed again by the dashboard or the saved-secret store. |
| `R2_IMAGE_BUCKET` | Sensitive identifier | Existing JPEG bucket. Must differ from DICOM bucket for public-image mode. | Cloudflare R2 bucket inventory. Preserve object keys; do not create an empty replacement and call migration done. |
| `R2_DICOM_BUCKET` | Sensitive identifier | Existing private original-DICOM bucket. | Cloudflare R2 bucket inventory. Keep public access disabled; do not add a public custom domain. |
| `R2_IMAGE_PUBLIC_BASE_URL` | No | HTTPS custom domain for public JPEG delivery; empty/omitted uses private signed image URLs. | R2 image bucket Custom Domains plus DNS/cache/TLS configuration. This publication choice requires approval. |
| `R2_SIGNED_URL_SECONDS` | No | Default300 seconds; signed URL lifetime/metadata freshness, not CDN JPEG TTL. | Operator policy. Public URLs do not gain signatures or change every300seconds. |
| `DICOM_RETENTION_ENABLED` | No | Default false; explicit opt-in for retaining uploaded originals. | Approved data-retention policy; preserve current choice during migration. |
| `CASE_MEDIA_DUAL_WRITE` | No | Default false; updates normalized projection alongside legacy writes. | Approved migration state; preserve rather than infer. |
| `CASE_MEDIA_NORMALIZED_READ` | No | Default false; enabling requires dual-write and reconciled projection. | Separate data-reconciliation approval, not a routine portability setting. |
| `MAX_UPLOAD_FILES` | No | Omit/empty means inherited unlimited file count; otherwise integer count. | Approved capacity policy; no assumption that total-byte limits imply a file-count cap. |
| `MAX_IMAGE_UPLOAD_BYTES` | No | Default33554432 (32MiB) per image. | Reviewed upload policy; omit optional integer rather than blank. |
| `MAX_CASE_UPLOAD_BYTES` | No | Default268435456 (256MiB) aggregate case. | Reviewed upload policy. |
| `MAX_IMAGE_PIXELS` | No | Default40000000 pixels per decoded image. | Reviewed decompression/memory policy. |

## Email
| Variable | Classification | Purpose / constraint | Source or recovery |
| --- | --- | --- | --- |
| `EMAIL_PROVIDER` | No | resend or custom; default custom. | Choose approved SMTP provider, not a browser login provider. |
| `EMAIL_HOST_PASSWORD` | Yes | SMTP password; in resend mode this is a Resend API key. | Resend dashboard API Keys: approved sending scope and verified domain. Existing key from private config; if unavailable, create replacement and update dependents. In custom mode obtain SMTP/app password from that provider. |
| `DEFAULT_FROM_EMAIL` | No | Verified sender required for resend; custom default noreply@localhost. | Approved sender on Resend verified sending domain/provider; not an arbitrary mailbox. |
| `DEFAULT_REPLY_TO_EMAIL` | No | Optional single email address; empty omits Reply-To. | Approved monitored reply address, or intentionally empty. |
| `EMAIL_BACKEND` | No | Custom mode only; default console, so not delivery-ready. Resend forces Django SMTP backend. | Use approved backend; preview forces dummy and tests use locmem. |
| `EMAIL_HOST` | No | Custom SMTP host; ignored by resend mode (smtp.resend.com). | Provider SMTP instructions. |
| `EMAIL_PORT` | No | Custom default587; resend forced587. | Provider instructions; this code uses STARTTLS, not implicit SSL. |
| `EMAIL_HOST_USER` | Sensitive identifier | Custom SMTP username; resend forced resend. | Provider SMTP instructions/account. |
| `EMAIL_USE_TLS` | No | Custom default true; resend forced true. | Provider STARTTLS requirement. EMAIL_USE_SSL=false and timeout20s are code constants, not environment inputs. |

## Filesystem and connector
| Variable | Classification | Purpose / constraint | Source or recovery |
| --- | --- | --- | --- |
| `STATIC_ROOT` | No | Collected static destination; production Compose /app/.local/static. | Named static volume seeded explicitly with selected image collectstatic; not uploads or a credential backup. |
| `MEDIA_ROOT` | No | Filesystem JPEG path for isolated/local mode; default /app/.local/media. | Separate persistent volume if filesystem mode is deliberately used; not a public mount of original media. |
| `PRIVATE_DICOM_ROOT` | Sensitive path | Private originals path in filesystem mode; default /app/.local/private-dicom. | Separate protected volume outside any public media route; production r2 uses private bucket instead. |
| `SQLITE_PATH` | Sensitive path | Only sqlite mode; default /app/.local/db.sqlite3. | Local/test path; not used by PostgreSQL Compose. Never use as a production DB backup recipe. |
| `TUNNEL_TOKEN` | Yes | Official cloudflared runtime connector token, connector file only. | Cloudflare Networking > Tunnels > selected tunnel > Add a replica. Never run a copied install command to obtain it. Rotation blocks new connections with old token; update all replicas deliberately, do not rotate merely to migrate. |

## Runtime and tooling names that are not application secrets

`PATH`, `LANG`, `PYTHONUNBUFFERED` and `PYTHONDONTWRITEBYTECODE` come from the
base image/Dockerfile and are not per-installation credentials. `POSTGRES_DB`,
`POSTGRES_USER`, `POSTGRES_PASSWORD` are inputs to the synthetic PostgreSQL
container, populated by Compose from fixed synthetic names and
`DATABASE_PASSWORD`; they are not extra production DB credentials. The standard
Docker/Compose options such as project name or Docker credentials are operator
tooling, not Django application settings. GitHub PATs, SSH keys, sudo credentials,
Cloudflare management/Access service credentials and registry logins may be
needed by operators, but must not be passed into the portal web container.
Custom cloudflared flags or management scripts are not an expanded application
API: audit any newly introduced variables separately.

## Portability does not package external state

- **Code/runtime:** build the selected commit using `Dockerfile`, or retain/load
  the exact audited runtime archive. Verify its checksums/Image ID. There is no
  promise that an explicit local tag is published to a registry or that a CI
  artifact remains available forever. Keep dependency/base image provenance.
- **Database:** the production recipe connects to an existing Azure server; it
  does not create, restore or migrate a database automatically. Allow the new
  VM in the provider network policy and verify DNS/TLS/role privileges. For the
  same server, retain DB and object-key mappings. For a different server, make
  a consistent backup, test restore/schema/extensions and reconcile writes.
  `migrate --plan` is inspection; an approved `migrate` is a separate action,
  not the default container start. Never run `seed_preview` on production.
- **Objects:** R2 JPEG and private-DICOM buckets remain external. Reuse approved
  buckets/jurisdiction/credentials if only moving the VM. Moving bucket/account
  requires a separate inventoried/hash-verified copy, key mapping and rollback
  plan. Unreferenced/private historical buckets and local originals are not
  automatically copied by Compose. No cleanup is implied by migration.
- **Volumes:** preview has its own synthetic DB/media/static volumes. Production
  only has collected static assets and the CA bind mount; rebuild static assets
  from the selected image into a new project/volume before web starts. Keep the
  old static tree and previous image for rollback. Never copy `/media` blindly
  into a public mount or lose private originals held outside R2.
- **Tunnel/DNS/security:** connector token is not an export of routing, Access,
  rate limits, cache/TLS rules or DNS. Inventory/export those privately through
  the owning account. Shared-tunnel replicas must reach every shared route,
  including non-web routes. This Compose does not reproduce SSH/other services.
  Validate separate synthetic tunnel and header/CSRF/Access behavior before an
  approved live switch. Existing Nginx/host-service deployments are not changed
  by merging these files.
- **Mail and ownership:** verified sending domain, DNS and sending permission
  remain provider-side prerequisites. Verify a scoped approved test after
  migration; ordinary startup never sends a test email. The operator needs
  access to the correct Azure, Cloudflare and Resend accounts, not merely a
  container image and filenames.
- **Rollback:** retain prior runtime/config, data backup and route compatibility.
  Once writes have happened, restore/reversion requires reconciliation. A new
  VM needs its own restart/backup/monitoring and shutdown policy; no old-host
  shutdown or destructive cleanup is part of these recipes.

## Provider references

- R2 S3 credentials and EU endpoint: https://developers.cloudflare.com/r2/api/tokens/
- Tunnel token and rotation: https://developers.cloudflare.com/tunnel/advanced/tunnel-tokens/
- Resend SMTP: https://resend.com/docs/send-with-smtp

The private installation inventory is kept separately from this public-safe
reference: exact account/server/bucket identifiers, host paths, secret custody,
current overrides, approved backup locations and access owners belong there.
The reference explains recovery routes without including credential values or
claiming that the image contains them.
