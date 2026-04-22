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

## Per-type blocking thresholds (must pass on BOTH metrics)

| Doc family | Term precision | Term recall | Def-text Jaccard |
|---|---|---|---|
| AR glossary | ≥95% | ≥85% | ≥85% |
| PAM glossary | ≥90% | ≥80% | ≥80% |
| FM/ATP/ADP/TC/TM glossary | ≥85% | ≥75% | ≥75% |
| Inline (overall) | ≥75% | ≥50% | ≥65% |

PR1.2 wheel publication is **gated on these thresholds passing**. Doc types failing their gate are removed from v1 scope (not blocking the whole release).

## File layout

```
validation_set/
├── README.md              ← this file
├── labels.example.yaml    ← format reference, NOT real labels
├── labels.yaml            ← real labels (gitignored until ready; commit only when all 30 PDFs are labeled)
└── pdfs/                  ← gitignored — symlink or copy your real PDFs here
    ├── AR_600-20.pdf
    ├── PAM_600-3.pdf
    └── ... (30 total)
```

## How to add labels

1. Drop the 30 real PDFs into `validation_set/pdfs/` (gitignored — large binaries).
2. Copy `labels.example.yaml` → `labels.yaml`.
3. For each PDF, label ~5 known-good definitions:

```yaml
documents:
  - pdf: AR_600-20.pdf
    doc_type: AR
    labels:
      - term: Combatant Command
        term_normalized: combatant command
        definition: A unified or specified command with a broad continuing mission...
        pdf_page_index: 142
        source_type: glossary
      - term: Permanent Change of Station
        term_normalized: permanent change of station
        definition: ...
        pdf_page_index: 87
        source_type: glossary
```

4. Run the validation suite locally:

```bash
pytest -m validation -v
```

The suite will:
- Load `labels.yaml`
- Run the extractor against each PDF
- For each `(doc_type, source_type)` group: compute term precision/recall + def-text Jaccard
- Fail the run with a per-type scorecard if any threshold is breached

5. Once all per-type gates pass, the harness emits `validation_set/scorecard.json` with the actual numbers; PR1.2 references this file when publishing the wheel.

## Why labels are kept out of git initially

- Real PDFs (~30 files × 1–10 MB each) are large; the repo stays lean.
- Hand-labeled definitions are the result of human review; partial sets create false confidence in CI.
- Once a complete labeled set lands in `labels.yaml`, gitignore it AND publish a SHA-256 of the canonical labels file in the PR1.2 release notes so reproducibility is provable without committing the corpus.

## Out of scope here

- ALARACT / EXORD / MILPER / memos / policy notices — v2 scope per parent plan §1.
- Inline-pattern expansion based on validation signal — PR1.3.
