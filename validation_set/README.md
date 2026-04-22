# Validation set

Real-PDF integration test set. Per parent plan §H8, **30 v1-scope PDFs** stratified by Army doc type:

| Doc type | Count |
|---|---|
| AR  | 15 |
| PAM | 5  |
| FM  | 4  |
| ATP | 3  |
| ADP | 1  |
| TC  | 1  |
| TM  | 1  |

## Per-type blocking thresholds

Recall + def-text Jaccard are **always** gated. Precision is gated **only** when explicit `negative_labels` are declared per PDF (sampled positive labels cannot fairly compute precision — see PR1.1 Codex iter-1 finding #1 in repo git log).

| Doc family | Term recall | Def-text Jaccard | Precision (only with negatives) |
|---|---|---|---|
| AR glossary | ≥85% | ≥85% | ≥95% |
| PAM glossary | ≥80% | ≥80% | ≥90% |
| FM/ATP/ADP/TC/TM glossary | ≥75% | ≥75% | ≥85% |
| Inline (overall, all doc types aggregated) | ≥50% | ≥65% | ≥75% |

PR1.2 wheel publication is **gated on these thresholds passing AND `passed_all: true` in `scorecard.json`**. Doc types failing their gate are removed from v1 scope (not blocking the whole release).

## File layout

```
validation_set/
├── README.md              ← this file
├── labels.example.yaml    ← format reference (committed)
├── labels.yaml            ← real labels (gitignored)
├── scorecard.json         ← derived (gitignored); written by harness
└── pdfs/                  ← gitignored — symlink or copy your 30 real PDFs here
    ├── AR_600-20.pdf
    └── ... (30 total)
```

## How to add labels

1. Drop the 30 real PDFs into `validation_set/pdfs/`.
2. Copy `labels.example.yaml` → `labels.yaml`.
3. Top-level `expected_stratification:` block declares the per-doc-type counts you commit to labeling. Harness fails loudly if your actual labeled docs don't reach that count — prevents incomplete corpora from emitting a passing scorecard.
4. For each PDF, label ~5 known-good `labels:` (positive cases). Format documented in `labels.example.yaml`.
5. **Optionally** add `negative_labels:` for terms the extractor MUST NOT emit (e.g., "Figure 1", "Chapter 3"). Required if you want precision gated; otherwise precision is informational only.
6. Run the validation suite locally:

```bash
pytest -m validation -v
```

The suite will:
- Assert the stratification gate (fails if labeled corpus is incomplete vs `expected_stratification`)
- Run the extractor against each PDF
- For each `(doc_type, source_type)` slice (inline rows aggregated under `*`): compute recall + def-text Jaccard, plus precision only where `negative_labels` exist
- Fail the run with a per-type scorecard if any threshold is breached
- Always write `validation_set/scorecard.json` with `passed_all: bool` at the top level — PR1.2 refuses to publish unless `passed_all: true`

## Why labels are kept out of git

- Real PDFs (~30 files × 1–10 MB each) are large; the repo stays lean.
- Hand-labeled definitions are the result of human review; partial sets create false confidence in CI.
- Once a complete labeled set lands in `labels.yaml`, gitignore it AND publish a SHA-256 of the canonical labels file in the PR1.2 release notes so reproducibility is provable without committing the corpus.

## Out of scope here

- ALARACT / EXORD / MILPER / memos / policy notices — v2 scope per parent plan §1.
- Inline-pattern expansion based on validation signal — PR1.3.
