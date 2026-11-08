# Additive case / series / image projection

This stage does not activate normalized readers or writers. Existing case Post
IDs, title routes, legacy columns and FilePost upload/viewer code remain in use.
Migration0044 creates empty tables only, with no automatic data backfill. No
real case data has been migrated. Future activation needs an equivalent verified
projection, dual-write coverage, object reconciliation and separate deployment
approval. Run the backfill only while legacy writes are stopped.

## Shape

- `Case.post_id` is the primary key and points to the existing Post. Clinical
  content, author and category remain on Post, not a competing case record.
- `Case.cover_key` preserves the first legacy cover selection. All distinct
  covers and legacy metadata values, including conflicting consent/tag/category
  values and NULL/blank, are retained once per case in `legacy_metadata`.
  A conflict is not silently resolved or treated as publication approval.
- One `Series` per nonempty plane per case. `sagital` retains the inherited
  spelling for compatibility; its label is Sagittal. Covers have their own
  series. Repeated cover keys are deduplicated; display slices are not.
- `Image.position` is zero-based FilePost-PK order, explicitly `legacy_pk`,
  never a claim about anatomical position. Each slice keeps its source row ID
  and raw description, even when descriptions differ. Source row IDs are scalar
  provenance, not cascading foreign keys to mutable legacy rows.
- Legacy object keys are preserved, not renamed or downloaded. New upload keys
  are already opaque in the existing pipeline. Legacy byte size/hash/location
  remain unknown and verification unverified. Metadata projection is not object
  integrity verification and is not proof of anonymization.
- Optional original-DICOM derivation link and conversion version are reserved
  for verified lineage. No legacy association or conversion version is invented.
  Display review defaults to pending; a schema field does not itself authorize
  publication or add an original-download route.

## Backfill and validation

`python manage.py case_media_backfill` is an aggregate, read-only dry run.
`--verify` compares every projected key, position, description and metadata value,
not only row counts. A SHA256 of the ordered legacy metadata detects source
changes. It is not an image-content hash. Neither command reads object storage
or creates signed URLs. Output contains aggregate counts, not image keys or case
content.

Applying requires `--apply --quiescent-source --expected-database <exact-name>`.
These guards reduce wrong-database mistakes; they do not grant production access
or approval. Do not apply against real data without separate approval. One
transaction per case supports retry: an identical existing projection is checked
and left unchanged. Changed source or corrupted projection stops, rather than
blindly overwriting. Earlier committed cases remain when a later case fails;
verify/reconcile before continuing. No objects or legacy rows are deleted.

Rollback of code before activation uses legacy readers unchanged. Reversing0044
would delete normalized manifest rows and must not be used after normalized-only
writes. This is not the cutover or rollback procedure for a production release.

## Deletion review

Case→Post, Series→Case and Image→Series follow the current case-deletion cascade
for display metadata only. This never deletes physical media. OriginalDicom has
PROTECT to Post and derived images use PROTECT to OriginalDicom, preserving the
existing retained-original guard. No user/account deletion policy is changed in
this stage. Reconciliation and final retention/deletion policy remain separate.

## Staged canonical dual-write

`CASE_MEDIA_DUAL_WRITE` defaults to false. When enabled in an isolated test
configuration, canonical create/edit saves the legacy rows and then refreshes
the normalized DB projection within the same transaction, after obsolete legacy
rows are removed. A projection failure rolls both sets of DB changes back.
Objects already written are not deleted on a DB failure; reconcile them as
unreferenced, do not blindly retry/delete. This is not a distributed transaction.

For new objects, the manifest records size and SHA256 of JPEG bytes sent and
known retained-original lineage with conversion version `educational-jpeg-v1`.
Object integrity remains unverified until separate read-back reconciliation;
review remains pending. A re-encoded JPEG is not proof of anonymization.

Migration0047 marks every pre-existing projection stale by default. Explicit
backfill/verification can clear it when source equivalence holds. Normal ORM
Post/FilePost saves and FilePost deletion, including the current admin, invalidate
existing projections. Canonical dual-write clears stale only after matching the
complete refreshed projection. Refresh resets display review to pending and case
review to legacy-unverified, never carrying approval onto changed images.

Direct SQL, `QuerySet.update`, `bulk_update` and `bulk_create` bypass save signals.
They must not be used for active media mutations without explicit invalidation
and reconciliation. Current normalized readers are NOT activated by this stage;
legacy code is still authoritative, so this limitation cannot silently serve
stale normalized data. A future reader activation must account for every write
path and must fall back on stale/unmigrated cases. Do not enable a reader merely
because the dual-write flag exists.

No new object is deleted by refreshing its display manifest. Retained original
manifests remain protected. No production flag, data, admin configuration or
public preview was changed during development.

## Staged normalized reader

`CASE_MEDIA_NORMALIZED_READ` defaults false and startup refuses it without
canonical dual-write enabled. It is not enabled by migrations. For a non-stale
projected case, cards use the selected cover, detail uses series counts and
slice endpoints select at most two object references by indexed explicit position
rather than OFFSET. Case URLs, audience, API fields and signing behavior remain
unchanged. Missing/unmigrated/stale cases fall back to the legacy reader.
A detected position gap returns unavailable, not an anatomically shifted slice.

Before enabling outside isolated tests, stop unsupported writes, complete
projection backfill and equivalence verification, reconcile every object with
read-back hashes/size and storage location, address metadata conflicts and
publication review separately, and test all routes. The stale marker covers
normal ORM/admin mutations, not direct SQL/bulk paths; those require explicit
invalidation and re-verification. A source fingerprint is metadata integrity,
not object integrity. Neither reader flag authorizes a media transfer, patient
publication or production cutover. No flag or real data was changed in this PR.

The first legacy row determines a card cover even if blank; later distinct
cover keys are retained in the manifest without silently changing that display
choice. This preserves the old card behavior exactly.

A stored expected image count is set only by checked backfill/canonical sync.
The slice reader checks count and min/max position against it before serving any
index. This catches interior and trailing deletions, not only a gap adjacent to
the requested slice. Migration0048 leaves existing counts unknown (NULL); the
reader returns unavailable until a separately authorized equivalence backfill
verifies and sets them. It never guesses that a shortened series is complete.

## Explicit read-back reconciliation

`python manage.py media_reconcile` reports aggregate manifest counts only and
reads no objects. `--read-objects` additionally requires the exact database name,
current storage label, a quiescent source declaration, a positive byte budget
and maximum object size. `--include-originals` is a separate opt-in, never the
default. These safeguards do not create permission for real data access or cost.
This command has only been tested on generated fixtures; no actual case object
was read or transferred during its development.

Read-back streams bytes into a size/SHA256 comparison. It does not sign URLs,
list buckets, upload, delete, rename, retry uncertain writes, update manifests,
adopt unknown legacy hashes or mark publication/integrity states approved.
Unknown baseline, mismatch, missing, unavailable storage, conflicting hashes for
a shared key, provider failure or exhausted limit produces an incomplete audit
and nonzero command result. Provider errors are not classified as absence, and
provider bodies/keys are not printed. Each shared key is read once; conflicting
reference metadata is reported, not silently skipped. A limit check may read one
extra probe byte before stopping; no further objects are attempted on read error
or byte-limit failure. Memory is bounded to1MiB chunks plus metadata.

Display objects are read only from the configured current backend; a manifest
pointing elsewhere is unavailable, not silently redirected. Originals, when
explicitly included, use their recorded private filesystem or distinct R2 bucket,
never a public download route. Remote404 responses without a filesystem-style
FileNotFoundError are reported conservatively as read errors, not known missing.

A clean audit compares referenced objects only. It does not prove no orphans
exist, no objects changed after the audit, or clinical anonymization. An orphan
inventory requires a separately authorized inventory/manifest and operator
reconciliation. Unknown legacy baselines need a trusted source manifest, not
accepting whatever bytes happen to be at a key. Partial-write cleanup stays a
manual explicit retention decision; nothing here deletes an uncertain object.
