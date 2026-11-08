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
