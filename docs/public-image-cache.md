# Public display-image caching

This option is for display-image buckets whose **entire contents** may be public.
It does not make private cases safe to publish. The original-DICOM bucket must
remain separate, with no custom domain or public development URL. This change
adds no DICOM URL generation or download route.

## Configuration and compatibility

- Default: leave `R2_IMAGE_PUBLIC_BASE_URL` empty. Display images keep the existing
  short-lived S3 URLs and private cache headers on new writes.
- Opt-in: set `R2_IMAGE_PUBLIC_BASE_URL` to the exact HTTPS origin of the image
  bucket's connected custom domain, for example `https://media.example.com`.
  Paths, query strings, fragments, credentials, ports and development/S3 URLs
  are rejected. Only `MEDIA_STORAGE=r2` with two distinct named buckets is valid.
- Keep the existing server-side R2 credentials, endpoint and bucket settings.
  A public URL is the origin plus the percent-encoded object key, without a
  signature, changing token, HEAD, GET or LIST request. Image keys in the database
  remain unchanged. Uploads and private reconciliation still use the S3 API.
- New image writes use `public, max-age=31536000, immutable` only in public mode.
  Atomic `IfNoneMatch="*"` writes remain in place. Never replace bytes under an
  existing key: use a new key for a changed image. DICOM always uses `no-store`.
- CSP adds the exact public origin only to `img-src`, never scripts or connections.
  Existing signed-image origins remain allowed for configuration rollback.
- HTML/account responses remain private and non-cacheable. Do not cache the case
  pages or slice JSON as part of this setup.

## Cloudflare preparation

No DNS, bucket-policy, metadata or production change is performed by the code.

1. Confirm the zone and image bucket are in the **same Cloudflare account**.
   R2 custom domains require this. A cross-account CNAME is not a substitute.
   If they differ, resolve account placement before proceeding. Moving only the
   images to another account also needs an application design for independent
   image/DICOM S3 identities, because the current configuration shares one S3
   endpoint and credentials. Do not move the zone or recopy objects by default.
2. Audit the image bucket's inventory before enabling public access. Connecting
   a custom domain publishes the whole bucket, not just currently referenced
   case images. There must be no originals, secrets or private files in it.
3. On the image bucket only: R2 > bucket > Settings > Custom Domains > Add/Connect
   Domain. Enter the chosen hostname, review the DNS record Cloudflare proposes,
   and wait for Active. Let this flow create the record; do not point a CNAME at
   the S3 API or `r2.dev`. Leave Public Development URL disabled on both buckets.
4. In the zone: Cache > Cache Rules, create a request Cache Rule named
   `Public display images - cache eligibility`. Match the exact media hostname,
   GET/HEAD methods and supported image extensions. Mark Eligible for cache.
   Keep Edge TTL and Browser TTL respecting origin headers. Check that no later
   matching rule overrides these settings. Do not apply this to the portal host.
   For this static, public image host only, select Cache Key > Ignore query string
   if offered. These object URLs do not use query-based variants, authorization or
   signatures. This reduces query-string cache busting. The current Cache Keys
   availability table lists Ignore query string on Free; stop for inspection if
   the console requests an upgrade. Do not change cache keys on signed S3 URLs.

Example expression, replacing only the example hostname:

```text
(http.host eq "media.example.com")
and (http.request.method in {"GET" "HEAD"})
and (lower(http.request.uri.path.extension) in {"jpg" "jpeg" "png" "webp"})
```

5. Existing objects may have `Cache-Control: no-store`. A custom domain and
   eligibility alone do not fix that. In Cache > Cache Rules > Cache Response
   Rules, create `Public display images - immutable successful responses`.
   Match the same expression plus `and (http.response.code eq 200)` and an image
   content type. Example additional condition:

```text
and (http.response.code eq 200)
and (http.response.headers["content-type"][0] in {"image/jpeg" "image/png" "image/webp"})
```

   Select Modify cache-control directives. Remove `no-store`, `private` and
   `no-cache`; set `public`, `max-age=31536000` and `immutable`. Leave
   **Cloudflare only off** for every directive, so browsers receive the policy
   too. Do not strip ETag, Last-Modified or Set-Cookie. Only successful image
   responses get the long policy; errors, challenges and non-images must not.
   This avoids rewriting existing objects or repeating a migration copy.
   Cache Response Rules are available on Free (10 rules) as well as paid plans.
   They run before cache evaluation. Ordinary Response Header Transform Rules
   run too late and are not an equivalent fix.
6. Smart Tiered Cache can reduce cold misses across edge locations. Verify its
   availability/terms before enabling. Do not enable paid Cache Reserve, Argo,
   Workers or an upgraded plan as part of this configuration.

If the console differs or rejects a field/directive, stop and inspect the actual
rule/schema. Do not substitute a zone-wide cache rule or change the bucket's
privacy by trial and error. The hostname example is not a verified active site.

## Verification before activation

Use a synthetic image first. Check the actual connected hostname and certificate,
then make two normal GETs for the exact same URL from the same client/location.
Expect a 200 image/jpeg (or supported image type), the long Cache-Control policy,
and a subsequent `CF-Cache-Status: HIT` with `Age`. A MISS on a cold cache is
normal. Do not use a query cache-buster or request `Cache-Control: no-cache`.
Inspect the returned image visually. Never claim caching works from DNS status
or response headers alone without a real cached GET.

Check an intentionally missing image: no long-lived error policy. Check the
original bucket still has no public domain/development URL and originals remain
inaccessible. Verify the real viewer's current/adjacent slices, CSP and navigation
with both legacy and normalized readers. Do not send credentials in browser URLs.
A single GET HIT does not prove the global hit ratio. Cache eviction, cold edge
locations, expiry and conditional revalidation can still read R2.

Cloudflare documents that a cache HIT avoids R2 operations. Cache misses and
revalidation can still incur Class B GET/HEAD requests. URL construction itself
uses no R2 operations. Application HEAD/LIST/reconciliation operations remain
metered. Cache is a cost reduction, not a spending cap or guarantee against bots
requesting many distinct images, varying other cache-key inputs, or cache-busting
query strings when Ignore query string has not been verified.

## Rollback and removal

To stop emitting public URLs, clear `R2_IMAGE_PUBLIC_BASE_URL` and restart the
candidate service. Signed URLs resume; no database rewrite, object move or schema
rollback is needed. Restoring the older application still requires the existing
media-recovery and deployment rollback procedure.

Clearing the variable does **not** revoke previously published URLs. To stop new
public retrieval, disable the bucket's custom domain and purge its CDN cache.
Check for other enabled public domains and `r2.dev` access separately. Already
cached browser copies cannot be recalled or purged remotely; a one-year immutable
policy is a real publication commitment. Deleting a case in the database does
not remove retained objects or cached copies. Future withdrawal of material
requires a separate retention/removal policy.

## Official references

- Same-account/custom domain and r2.dev limitations:
  https://developers.cloudflare.com/r2/buckets/public-buckets/
- R2 cache behavior and tiered caching:
  https://developers.cloudflare.com/cache/interaction-cloudflare-products/r2/
- Cache Response Rules, availability and precedence:
  https://developers.cloudflare.com/cache/how-to/cache-response-rules/
- Response-rule fields and directives:
  https://developers.cloudflare.com/cache/how-to/cache-response-rules/settings/
- Console steps:
  https://developers.cloudflare.com/cache/how-to/cache-response-rules/create-dashboard/
- Cache-rule settings and ordering:
  https://developers.cloudflare.com/cache/how-to/cache-rules/settings/
  https://developers.cloudflare.com/cache/how-to/cache-rules/order/
  https://developers.cloudflare.com/cache/how-to/cache-keys/
- Cache-Control semantics and browser-purge limitation:
  https://developers.cloudflare.com/cache/concepts/cache-control/
  https://developers.cloudflare.com/cache/how-to/edge-browser-cache-ttl/
- Operations and cache-hit billing:
  https://developers.cloudflare.com/r2/pricing/
  https://developers.cloudflare.com/billing/understand/how-charges-accrue/
