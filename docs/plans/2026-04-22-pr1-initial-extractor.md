# PR1 — Initial Extractor (sibling repo bootstrap)

**Date:** 2026-04-22
**Owner:** mw
**Parent plan:** [`sarahewilkerson/fedresearch` `docs/plans/2026-04-22-defined-terms-search.md`](https://github.com/sarahewilkerson/fedresearch/blob/main/docs/plans/2026-04-22-defined-terms-search.md)

## Phase 0.a Classification

**full-flow** — new repo, new pip-installable package, defines the JSON contract consumed by the FedResearch backend. Touches no production system directly but locks the contract that PR2 + PR4 build against.

## 1. Problem Statement

PR0 approved an umbrella plan for defined-terms search. PR1 delivers the **first-mover dependency**: a sibling repo `sarahewilkerson/fedresearch-dictionary-extractor` that produces structured JSON from Army regulation PDFs. Backend (PR2/PR4) installs this as a SHA-pinned wheel.

## 2. Scope (this PR)

**In scope:**
- Repo bootstrap (README, pyproject.toml, LICENSE, .gitignore)
- Package `fedresearch_dictionary_extractor` with v0.1.0 layout under `src/`
- Profile abstraction + `ArmyProfile` covering v1 doc types (AR/PAM/FM/ATP/ADP/TC/TM)
- Glossary extractor (ported and adapted from `FedResearch_Dictionary_Creator`, emitting dicts matching schema v1 instead of DOCX entries)
- Inline-definition extractor (NEW — minimal patterns, low confidence)
- Canonical `normalize_term()` algorithm + shared YAML fixture
- JSON output with schema validation (`schema/definition-output-v1.json`)
- CLI: single-doc + batch modes with `--gcs-key`, `--doc-id`, `--manifest`
- Intra-doc dedup (glossary preferred over inline; tiebreak by confidence then page)
- Dual page fields: `pdf_page_index` (1-indexed pymupdf) + `printed_page_label`
- Tests for normalize, dedup, CLI smoke
- GitHub Actions CI: lint + pytest on Python 3.11 + 3.12, wheel build job

**Deferred (follow-up cycles):**
- 30-PDF labeled validation set + per-type precision/recall thresholds (PR1.1)
- v0.1.0 GitHub Release with pinned wheel SHA (PR1.2 — gated on validation pass)
- Expanded inline patterns based on validation signal (PR1.3)
- Test coverage push to ≥85% (PR1.1)
- ALARACT/EXORD/MILPER/memo profiles (v2)

The split is deliberate: this PR establishes the repo, contract, and baseline implementation. Subsequent PRs validate quality before publishing the wheel that the backend Dockerfile will pin.

## 3. Approach

Followed parent plan §3.1 exactly:
- Output format: JSON-per-PDF, schema-validated.
- Inline tagged `source_type: "inline"`; backend assigns `visibility=PENDING_REVIEW` at ingest.
- Page numbers: dual `pdf_page_index` + `printed_page_label`.
- Dedup at emit time (not via DB constraint).
- Zero-entry PDFs emit valid JSON with `entries: []`.
- Normalization algorithm in `normalize.py` matches the byte-by-byte spec from parent plan §3.1; shared fixture lives at `tests/fixtures/normalization_cases.yaml`.

## 4. Hard 30%

- **H1 (carries from parent H1):** Inline extraction false positives. Mitigation: confidence capped at 0.65 for inline rows; backend defaults inline to `PENDING_REVIEW`. Pattern coverage intentionally narrow until validation set proves quality.
- **H2 (carries from parent H3):** Page-number correctness. Mitigation: dual fields per parent plan; `_safe_page_label` returns None when pymupdf has no label set.
- **H3 (carries from parent H9):** Normalization parity with backend. Mitigation: shared YAML fixture. Backend test suite must consume this same file; CI on both sides will fail if drift appears.

## 5. Blast Radius

- Repo is new and standalone; no production traffic depends on it until the wheel is published and the backend Dockerfile pins a SHA (PR4 territory, not PR1).
- Wheel is NOT published in this PR — that's PR1.2 after validation gate passes.
- Backend impact: zero in this PR.

## 6. Verification Strategy

- 32 tests pass locally (normalize fixture × 23 cases, dedup × 5, CLI smoke × 4)
- `python -c "from fedresearch_dictionary_extractor.json_output import validate; ..."` end-to-end smoke against the v1 schema (zero-entry + one-entry payloads validate)
- CI matrix runs ruff lint + pytest on 3.11 + 3.12
- CI builds the wheel and publishes the SHA-256 in the job log (becomes the input for the backend Dockerfile pin in PR4)

## 7. Documentation

- README describes scope (v1 doc types), CLI usage, schema location, install path
- This plan doc (PR1 implementation plan) lives in repo `docs/plans/`
- Schema lives at `src/.../schema/definition-output-v1.json` and is documented in README

## 8. Completion Criteria (this PR)

- [ ] Repo exists on GitHub (`sarahewilkerson/fedresearch-dictionary-extractor`)
- [ ] Package importable: `from fedresearch_dictionary_extractor import __version__` returns `"0.1.0"`
- [ ] CLI `extract-definitions --version` prints `extract-definitions 0.1.0`
- [ ] All 32+ tests pass on local Python 3.11
- [ ] CI workflow is configured (will need real CI run on PR to verify green)
- [ ] PR opened against repo's `main`

## 9. Out of Scope (gated to follow-up cycles)

- Validation set with per-type thresholds → PR1.1
- v0.1.0 GitHub Release with wheel + SHA → PR1.2
- Expanded inline patterns → PR1.3
- Real-PDF integration test (requires committing test fixtures) → PR1.1
- ≥85% line coverage → PR1.1

## Sync Verification

(populated post-merge)
