# Case query bounds and index evidence

## API pagination

`GET /api/get/posts/` remains token-authenticated and returns the existing JSON
array and item schema, including the intentionally exposed author email.
Responses now contain at most 50 cases by default. `page_size` accepts 1-100.
Follow the HTTP `Link` header with `rel="next"` until absent. Clients that used
the old unbounded export must follow this header to retrieve the full collection.
`after` is an exclusive non-negative case PK, not an offset. No count query is
needed. Appended cases may appear in later pages; this is not a snapshot export.

## Reproducible synthetic measurement

Measured with PostgreSQL 18.6 in an isolated container with no network or exposed
ports, generated data only, 50,000 rows, about 660 bytes of content per row,
1,000 repeated timestamps and 10 selective title matches. The container and its
in-memory data were deleted. These are query-level examples, not latency promises
for a live environment or measurements of real case data.

Three `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` runs per query/phase; the final run:

| Query | Before | After | Plan change |
| --- | ---: | ---: | --- |
| Latest five `(date_posted DESC, id DESC)` | 23.840 ms | 0.075 ms | sequential scan + top-N sort to index-only scan |
| Case-insensitive substring count, title OR content | 288.749 ms | 0.178 ms | sequential scan to BitmapOr of expression GIN indexes |

Index sizes in this fixture: date+ID 1,589,248 bytes, title trigram 2,318,336 bytes,
content trigram 2,449,408 bytes. GIN adds storage and write costs. Short/common
searches may still use a sequential scan. Search behavior remains Django
`icontains`, including its escaping, not tokenized full-text or fuzzy search.
Expression indexes match its PostgreSQL `UPPER(column) LIKE UPPER(parameter)`.

Equivalent fixture setup:

```sql
CREATE TABLE fixture(id bigint PRIMARY KEY, title varchar(100), content text,
                     date_posted timestamptz);
INSERT INTO fixture
SELECT n, CASE WHEN n % 5000 = 0 THEN 'Synthetic rareword'
               ELSE 'Generated fixture ' || n END,
       repeat('Generated synthetic content only. ', 20),
       '2026-01-01'::timestamptz + (n % 1000) * interval '1 minute'
FROM generate_series(1, 50000) n;
ANALYZE fixture;
-- Run each query before and after the candidate indexes.
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id FROM fixture ORDER BY date_posted DESC, id DESC LIMIT 5;
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT count(*) FROM fixture
WHERE UPPER(title::text) LIKE UPPER('%rareword%')
   OR UPPER(content::text) LIKE UPPER('%rareword%');
CREATE INDEX fixture_date_id ON fixture(date_posted DESC, id DESC);
CREATE EXTENSION pg_trgm;
CREATE INDEX fixture_title_trgm ON fixture USING gin(UPPER(title) gin_trgm_ops);
CREATE INDEX fixture_content_trgm ON fixture USING gin(UPPER(content) gin_trgm_ops);
ANALYZE fixture;
```

## Deployment caveats

No migration has been applied to a real case database. Migration 0003 adds a
small B-tree index using Django's normal schema operation and therefore needs a
planned lock window. Migration 0004 runs concurrent PostgreSQL index builds
outside a transaction and requires permission to enable `pg_trgm`. SQLite skips
that PostgreSQL-only migration. Reversal removes its two indexes, not the shared
extension. An interrupted invalid concurrent index causes an explicit error
rather than silently passing a retry; inspect it before manual cleanup/retry.
