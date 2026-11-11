# Domain and account-email policy

No real database has been migrated by this change. Before any real deployment,
run `python manage.py domain_preflight` with separately authorized read access.
It reports aggregate counts only. Resolve collisions/invalid legacy values with
explicit owner decisions, not automatic account merges, deletion or clinical
rewrites. Database constraints can block deployment until those issues are fixed.
Normal schema/index operations require a planned lock window and rollback check.

## Confidence and domain values

New cases default to `Sin evaluar` (unevaluated), not high confidence. Existing
high-confidence and other records are not rewritten or downgraded. Legacy blank
confidence remains allowed as unspecified. Choice lists for categories/confidence,
legacy format/consent and retained-original metadata now have database checks.
Legacy nullable/blank optional fields remain compatible: this stage does not
rewrite NULL into an empty string or claim both mean clinical consent.

The original-DICOM hash must be64 lowercase hex characters, size positive,
storage location known and key nonempty. These checks validate shape, not object
existence, content, anonymization or publication authority.

## Account email

Account email identity is `LOWER(TRIM(email))`. Blank values are allowed for
accounts without email but are never login identifiers. New signup email is
lowercased and trimmed; login and password-reset lookup use the same database
expression. A collision fails closed, never selecting an arbitrary account.

A partial expression unique index enforces this under concurrent writes, not
only in the form. Migration0046 first reports the number of colliding normalized
email groups and stops if nonzero, without printing addresses or modifying
accounts. It then creates the index; a concurrent collision still fails the
index build rather than bypassing uniqueness. Reversal removes only this index,
not users or their original address values. Existing addresses are not rewritten.
Signup catches an insertion race before sending its activation message. Profile
operations use the authenticated user directly rather than finding them by email.
The API's intentional author-email field and existing case audience are unchanged.

Lowercase/trim is an explicit portal policy, not a claim that every mail system
uses identical local-part semantics. No new email, recipient, or notification was
sent while developing or testing this change; tests use generated invalid-domain
addresses and the in-memory backend.

## Deletion and remaining work

No CASCADE relationship is changed here. User→Post→legacy display metadata keeps
the inherited behavior. OriginalDicom PROTECT to Post and Image PROTECT to original
remain in force. Database metadata deletion does not delete storage objects.
Actual object deletion, retention exceptions and account deletion need a separate
policy and reconciliation workflow. The current optional-field NULL/blank policy
is compatible, not a lossy normalization of historical clinical data.
