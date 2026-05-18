# Extraction Cohort Definitions

Canonical SQL predicates for the FedResearch dict-extractor failing-cohort
work. Used by the backend repo's operator-UPDATE re-extraction commands
and by this repo's per-unit acceptance scripts.

## Failing-cohort (post-extraction zero-entry-with-glossary)

**v0.5.0+ predicate (current):**

```sql
SELECT q.document_id, d.canonical_id, d.gcs_key
FROM definition_extraction_queue q
JOIN documents d ON d.id = q.document_id
WHERE q.status = 'SUCCEEDED'
  AND q.extractor_version = '<current_extractor_version>'
  AND q.entry_count = 0
  AND d.extracted_text_status = 'HAS_TEXT'
  AND d.extracted_text ILIKE '%glossary%'
  AND length(d.extracted_text) > 100000
  AND d.total_pages >= 30          -- NEW v0.5: exclude Class-4 short docs
ORDER BY q.document_id;
```

### v0.5.0 rationale (Class-4 short-doc exclusion)

D-2's findings memo identified 7 of 45 docs in the original v0.4 residual
cohort as Class-4: short docs (<10 pages of real content) where the word
"glossary" appears in a footnote or cross-reference, but the doc has no
actual glossary section. These docs aren't extraction failures — they
have nothing to extract.

The `length(extracted_text) > 100000` floor (originally intended to
exclude short docs) didn't help: some Class-4 docs have substantial OCR'd
text that exceeds 100KB despite having few pages.

The `total_pages >= 30` floor is empirically reliable: every Army Pub
in the v0.4 successful-extraction cohort has ≥30 pages. Docs below this
threshold are reference cards, change pages, or brief memos — none have
glossary sections.

### Pre-v0.5 (deprecated)

```sql
-- v0.4 / v0.5-pre-cohort-cleanup predicate (deprecated 2026-05-18)
-- Lacked total_pages floor; over-included 7 short docs as Class-4 false
-- positives.
```

## How to use

For an operator-UPDATE re-extraction wave (paired with a new EXTRACTOR_VERSION
bump in the backend):

```sql
UPDATE definition_extraction_queue
SET status = 'PENDING', extractor_version = NULL,
    failure_reason = NULL, error_snippet = NULL, attempts = 0,
    last_attempt_at = NULL, next_attempt_at = NULL
WHERE status = 'SUCCEEDED' AND extractor_version = '<prior_extractor_version>'
  AND entry_count = 0
  AND document_id IN (
    SELECT d.id FROM documents d
    WHERE d.extracted_text_status = 'HAS_TEXT'
      AND d.extracted_text ILIKE '%glossary%'
      AND length(d.extracted_text) > 100000
      AND d.total_pages >= 30
  );
```

Substitute the prior `extractor_version` (e.g., `army-v2.2.0` for the
v0.5.0 wave starting from D-1's v0.4.0 state).

## History

- **2026-05-17:** original v0.4 → v0.5 re-extraction used the SQL without
  the page-count floor. 177 docs flipped; 132 recovered, 45 stayed zero.
  Of the 45, 7 were Class-4.
- **2026-05-18:** v0.5.0 release-gate uses the new predicate with
  `total_pages >= 30`.
