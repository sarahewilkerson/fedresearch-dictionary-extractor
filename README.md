# fedresearch-dictionary-extractor

Extracts **defined terms** (glossary + inline definitions) from Army regulation PDFs and emits structured JSON for ingestion by [FedResearch](https://github.com/sarahewilkerson/fedresearch).

Sibling to the main FedResearch application. Versioned independently; backend installs a SHA-pinned wheel at build time (see `PACKAGING.md`).

## Status

**v0.1.0 (in development)** — PR1 of the defined-terms-search feature train. See [FedResearch plan](https://github.com/sarahewilkerson/fedresearch/blob/main/docs/plans/2026-04-22-defined-terms-search.md) for full context.

## Scope

**v1 covers these Army doc types:** `AR`, `DA PAM`, `FM`, `ATP`, `ADP`, `TC`, `TM`. These have glossary sections that parse reliably.

**Deferred to v2:** `ALARACT`, `HQDA EXORD`, `MILPER`, `DA memoranda`, `HQDA policy notices` — these rely primarily on inline extraction, which carries higher false-positive risk.

## Install

```bash
pip install fedresearch-dictionary-extractor
```

Or for backend Docker-image installs with SHA pinning, see the wheel URL + SHA-256 on each GitHub Release.

## CLI

```bash
# Single PDF (for NestJS subprocess call)
extract-definitions \
  --input /path/to/AR_600-20.pdf \
  --output /path/to/out.json \
  [--profile army] \
  [--gcs-key "Regs - Army Pubs/AR_600-20.pdf"] \
  [--doc-id ckx1y2z...]

# Batch mode (for local backfill)
extract-definitions \
  --input-dir ~/army_pdfs \
  --output-dir ~/army_defs \
  --manifest ~/manifest.json \
  --workers 8
```

## Output schema

See `docs/schema/definition-output-v1.json`. Every output includes:

- `schema_version: "1"`
- `source_pdf`, `source_gcs_key`, `source_doc_id`, `source_pub_number`, `source_doc_type`
- `extractor_version`, `extraction_timestamp`, `profile`, `text_sha256`
- `entries[]` — each with `term`, `term_normalized`, `definition`, `source_type` (glossary|inline), `section`, `pdf_page_index`, `printed_page_label`, `confidence`, `flags[]`
- `metadata` — page counts, glossary pages, entries per source type, post-dedup count

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                  # default suite (excludes real-PDF validation)
pytest -m validation    # opt-in: requires validation_set/labels.yaml + pdfs/
ruff check src tests
```

## Validation set

Per-doc-type precision/recall + def-text Jaccard thresholds gating PR1.2 wheel
publication live in `validation_set/`. See [`validation_set/README.md`](validation_set/README.md)
for label format, threshold table, and stratification target (30 PDFs total).
Real PDFs and labels are kept out of git; the harness skips cleanly when
`labels.yaml` is absent.

## License

MIT — see LICENSE.
