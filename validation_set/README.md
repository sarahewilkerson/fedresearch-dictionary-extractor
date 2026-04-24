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
├── README.md                          ← this file
├── labels.example.yaml                ← format reference (committed)
├── labels.yaml                        ← real labels (gitignored)
├── scorecard.json                     ← derived (gitignored); written by harness
├── classifier_snapshot_prefix.yaml    ← immutable pre-fix regression baseline (committed — PR-classifier-B)
├── classifier_snapshot.yaml           ← current classifier verdicts over candidate-output/*.json (committed)
├── candidate-output/*.json            ← pre-fix extractor output per PDF (committed — used by the auto-classifier)
└── pdfs/                              ← gitignored — symlink or copy your 30 real PDFs here
    ├── AR_600-20.pdf
    └── ... (30 total)
```

### Regression oracle for classifier changes (PR-classifier-B)

When modifying `src/fedresearch_dictionary_extractor/labels_classifier.py`:
- `classifier_snapshot_prefix.yaml` is the **immutable** pre-fix baseline. NEVER regenerate.
- `classifier_snapshot.yaml` is the **current** state. Regenerate via `python3 scripts/refresh_classifier_snapshot.py` after any classifier change.
- `tests/fixtures/option_b_expected_flips.yaml` enumerates the terms expected to flip `b`→`g` for PR-classifier-B (independent of the `FLIPS_BAD_TO_GOOD` dict, which is now empty).
- `tests/test_labels_classifier.py::test_no_unexpected_classifier_flips` asserts that the diff between the two snapshot files equals exactly the fixture's flip set. Any drift is flagged.
- When a corpus change (e.g., extractor tightening) deliberately removes entries from `classifier_snapshot.yaml`, the removed (pdf, source_type, term) tuples must be added to `REMOVED_SINCE_PREFIX` in the same test file. The test uses exact-set equality on both removed-keys and added-keys — silent drift in either direction fails loud. `classifier_snapshot_prefix.yaml` retains "ghost" entries for the removed terms and stays immutable.

## Two-tier label oracle (PR1.2-quality)

The harness reads two confidence tiers from `labels.yaml`:

**Tier 1 — user-confirmed (BLOCKING):**
- `tier1_positive_terms[]`: terms the user confirmed appear in the doc, gated on **term-presence only** (no Jaccard). The fix is allowed to legitimately change definitions; the term must still be present.
- `negative_labels[]`: terms that MUST NOT appear in extractor output. Tier-1 fails the run.

**Tier 2 — auto-classified (INFORMATIONAL only, never blocks):**
- `auto_positive_labels[]`: heuristically-classified-good terms (recall reported as warning if low)
- `auto_negative_labels[]`: heuristically-classified-bad terms (count of violations reported)

**Stage 1 (this PR):** `labels` (Jaccard-gated key in the existing harness) is left empty — the fix legitimately changes defs and there are no canonical user-confirmed defs yet. Stage-1 gates only on Tier-1 (term-presence + negative_labels).

**Stage 2 (PR1.2 wheel publication):** populate `labels[]` with user-confirmed canonical defs from batches 2+3, re-enabling Jaccard gating + the existing per-type recall thresholds.

**Bold-fallback exclusion:** docs that fell back to legacy X-only gating (signalled by `metadata.glossary_used_legacy_fallback=true` in the analyzer output) are excluded from Tier-1 negative-label gating. Rationale: the fix didn't fire on those docs, so penalizing them for not improving = wrong signal. Tracked in `scorecard.json` `fallback_docs`.

## How to add labels

1. Drop the real PDFs into `validation_set/pdfs/`.
2. Copy `labels.example.yaml` → `labels.yaml`.
3. Top-level `expected_stratification:` block declares the per-doc-type counts you commit to labeling. Harness fails loudly if your actual labeled docs don't reach that count — prevents incomplete corpora from emitting a passing scorecard.
4. For each PDF reviewed by a human, populate `tier1_positive_terms[]` (presence-only positives) and `negative_labels[]` (must-not-appear).
5. For non-reviewed PDFs, the auto-classifier populates `auto_positive_labels[]` / `auto_negative_labels[]` (informational only).
6. **At Stage 2:** populate `labels[]` with full term + canonical definition + page from user review of batches 2+3 to enable Jaccard gating per the existing harness.
7. Run the validation suite locally:

```bash
pytest -m validation -v
```

The suite will:
- Assert the stratification gate (fails if labeled corpus is incomplete vs `expected_stratification`)
- Run the extractor against each PDF
- `test_tier1_oracle`: BLOCKING — Tier-1 positive recall ≥95%, Tier-1 negative violations = 0
- `test_per_type_thresholds`: BLOCKING when `labels[]` populated (Stage 2) — per-type recall + Jaccard + precision gates
- Always write `validation_set/scorecard.json` with `tier1.passed: bool`, `tier2.*` (informational), `per_doc_metrics`, `fallback_docs`

## Why labels are kept out of git

- Real PDFs (~30 files × 1–10 MB each) are large; the repo stays lean.
- Hand-labeled definitions are the result of human review; partial sets create false confidence in CI.
- Once a complete labeled set lands in `labels.yaml`, gitignore it AND publish a SHA-256 of the canonical labels file in the PR1.2 release notes so reproducibility is provable without committing the corpus.

## Out of scope here

- ALARACT / EXORD / MILPER / memos / policy notices — v2 scope per parent plan §1.
- Inline-pattern expansion based on validation signal — PR1.3.
