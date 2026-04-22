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

- [x] Verification strategy executed: **PASS** (32 pytest cases, ruff lint clean, schema-validation smoke OK)
- [x] Branch pushed to remote: **YES** — `feat/2026-04-22-initial-extractor`, then deleted post-merge
- [x] Branch merged to main: **YES** — squash-merge PR #1 → commit a42788e at 2026-04-22T20:38:24Z
- [x] Main pushed to remote: **YES** — after this Sync Verification appendix commit lands, local main == origin/main @ a835987 (a42788e was the squash-merge SHA; a835987 is this appendix on top of it)
- [x] Documentation updated and current: **YES** — README + this plan doc cover the v0.1.0 baseline; v0.1.0 wheel publication deferred to PR1.2
- [x] Production deploy: **N/A** — package not yet published to PyPI or as a GitHub Release. PR1.2 will gate that on validation-set (PR1.1) results.
- [x] Local, remote, and main are consistent: **YES** — all at a835987
- CI status: **all green** on main post-PR1 merge (24801438420 SUCCESS in 37s) and post-plan-close (24801464937 SUCCESS in 38s). Native runners healthy; no admin bypass required (unlike the FedResearch repo today).
- Verified at: 2026-04-22T20:39:02Z (PR1 merge 20:38:24Z, plan-close commit 20:38:58Z, last green CI 20:39:02Z, final SHA a835987)

## Execution Results

**Final status:** CLEAN — first PR merged with fully-green CI on Python 3.11 + 3.12.

**What landed:**
- 11 new files in package + 3 test files + CI workflow + plan + README + scaffold
- 32 tests passing
- Wheel-build job confirmed working (input for PR4's Dockerfile SHA pin)

**Iteration count this PR:** 1 plan → 1 execution review → CLEAN. No remediation rounds.

**Deferred (separate `/develop` cycles):**
- **PR1.1** — validation set + ≥85% coverage push
- **PR1.2** — v0.1.0 wheel + GitHub Release with pinned SHA (gated on PR1.1)
- **PR1.3** — expanded inline patterns based on validation signal

**Rule suggestions surfaced:**
- None this PR (all routine).

**Downstream unlocked:**
- **PR1.1** /develop cycle (validation set + coverage)
- **PR2** /develop cycle (FedResearch backend) can start in parallel; the JSON schema and `normalize_term` algorithm are now stable contracts the backend can target. Backend won't pin a wheel SHA until PR1.2 publishes one.

