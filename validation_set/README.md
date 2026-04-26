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

## Honest artifact status (2026-04-26)

The validation_set has accumulated artifacts at varying confidence levels. Read this section before treating any single artifact as ground truth.

**Canonical corpus audit:** [`manifest_audit.md`](./manifest_audit.md) (committed) — generated 2026-04-26 per Sub-Unit 1a of the v0.2.0 decomposition. Records the actual counts, malformed filenames, manifest gaps, reconciliation matrix, and DA-PAM normalization rule. **Cite this doc as source-of-truth for corpus state**, not the per-artifact counts in older PR1.x plan docs.

**Artifact roles (post-audit):**

| Artifact | Status | Confidence |
|---|---|---|
| `pdfs/` (30 files; gitignored) | Real PDF source set; 27 well-formed `.pdf` + 3 malformed (1 truncated `.p` extension, 2 extensionless) | High — actual files |
| `manifest.json` | Local↔GCS mapping for 27 of 30 PDFs (3 short-name PDFs lack manifest entries) | High |
| `candidate-output/*.json` | v0.1.0 extractor outputs, 27 JSONs + `NO_DEFINITIONS.txt` sentinel | High — pinned at v0.1.0 |
| `labels.yaml` | Tier-1 hand-confirmed labels for thresholded harness; gitignored | High when populated |
| `labels-batch1.yaml` | 5 hand-flips from 2026-04-22 spot-check; **indices DRIFTED vs current candidate-output** | Medium — content stable, indices stale |
| `batch1_reconciled.yaml` | 2 forbidden_pairs reconciled to current candidate-output by content (TC + FM) + 3 unresolvable_flips documented; Sub-Unit 1b deliverable | High for the 2 pinned pairs |
| `labels-pending.tsv` | 866 rows × 19 docs; **`label` column EMPTY across all rows; `auto_guess` carries g/b classification** — auto-classifier output AWAITING human review, NOT a hand-vetted oracle | Low — informational only |
| `classifier_snapshot.yaml` / `classifier_snapshot_prefix.yaml` | Pre/post snapshots for the labels-classifier regression test (PR-classifier-B) | High — covered by `test_no_unexpected_classifier_flips` |

**Two oracles in default CI** (no `validation` marker):

1. `tests/test_labels_classifier.py::test_no_unexpected_classifier_flips` — pre/post classifier snapshot equality (existing).
2. `tests/test_batch1_reconciled.py::test_v0_1_0_corpus_pin_emits_known_forbidden_pair` — corpus pin against candidate-output for the 2 reconciled batch1 forbidden pairs (added 2026-04-26 per Sub-Unit 1b).

The corpus-pin test is intentionally a baseline pin, not an extractor regression test. When Unit 3 (Section II scoping) lands and candidate-output is regenerated under the fixed extractor, this test fails — that's the intended signal. See `tests/test_batch1_reconciled.py` module docstring for the lifecycle (invert / replace / re-pin decision rule).

**Provenance drift caveats:**

- `labels-batch1.yaml`'s flip indices were captured 2026-04-22; current candidate-output may have been regenerated since. Use `batch1_reconciled.yaml` (content-resolved) instead.
- `labels-pending.tsv` was generated from a different extractor build; corpus-wide byte-exact prefix match is 468/698 g rows + 9/168 b rows present in current candidate-output. Treat the TSV as informational baseline material, not ground truth.
- `manifest.json` covers 27 of 30 PDFs. The 3 missing entries (`AR_600-20.pdf`, `PAM_600-3.pdf`, `TC_1-19.30.pdf`) are short-name fixtures separate from the manifest's long-name conventions.

**Naming alias:** JSON `source_pub_number` uses `DA PAM`; `labels-pending.tsv` uses `PAM`. When joining, normalize via `s.replace('DA PAM ', 'PAM ')`. Affects 6 JSONs (3 referenced from TSV: PAM 190-45, PAM 350-58, PAM 71-32).

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
├── manifest_audit.md                  ← canonical corpus state, generated 2026-04-26 (Sub-Unit 1a)
├── manifest.json                      ← local↔GCS path mapping (committed; covers 27 of 30 PDFs)
├── labels.example.yaml                ← format reference (committed)
├── labels.yaml                        ← real labels (gitignored)
├── labels-batch1.yaml                 ← 2026-04-22 hand-flips (committed; indices DRIFTED — see manifest_audit.md)
├── batch1_reconciled.yaml             ← Sub-Unit 1b: 2 forbidden_pairs (content-reconciled) + 3 unresolvable
├── labels-pending.tsv                 ← auto-classifier output (committed; label column EMPTY — informational)
├── scorecard.json                     ← derived (gitignored); written by harness
├── classifier_snapshot_prefix.yaml    ← immutable pre-fix regression baseline (committed — PR-classifier-B)
├── classifier_snapshot.yaml           ← current classifier verdicts over candidate-output/*.json (committed)
├── candidate-output/*.json            ← v0.1.0 extractor output per PDF (committed)
└── pdfs/                              ← gitignored — symlink or copy your 30 real PDFs here
    ├── AR_600-20.pdf
    └── ... (30 total; 27 well-formed + 3 malformed; see manifest_audit.md)
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
