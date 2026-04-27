# PR-A — extractor correctness fixes for v0.3.0

## Phase 0.a Classification

**fast-path-eligible** — six surgical correctness fixes plus one dep cleanup; all reversible (git revert restores all). Single repo. Ships v0.3.0 wheel; backend lockstep PR (`fedresearch` repo, branch `feat/2026-04-27/dict-wheel-v0.3.0-pin`) bumps `EXTRACTOR_VERSION` from `army-v2.0.0` → `army-v2.1.0` to invalidate the worker's idempotency cache and force re-extraction.

This plan is one of four PRs in a stacked program. Companion docs live in the `fedresearch` repo at `docs/plans/2026-04-27-pr-{a-pin,b,c,d}-*.md`. Cross-cutting parent plan: `~/.claude/plans/login-to-hetzner-review-misty-moler.md` (ephemeral; this doc is the canonical source-of-truth).

## 1. Problem statement

v0.2.0 shipped Section II range scoping (Unit 3). Three orthogonal bug classes survive into the deployed wheel and one operational gap blocks downstream caching:

1. **Inline extractor over-match (CHANGELOG.md line 33).** TC 1-19.30 page 102 body fragment `dampen \nusually` is extracted as a definition. The inline `For purposes of… X means Y` regex matches mid-sentence body text because it lacks a sentence-boundary anchor and accepts lowercase term tokens. Confirmed in v0.2.0 candidate-output by `tests/test_batch1_reconciled.py:13-14`.
2. **Asterisk-prefix term split (CHANGELOG.md line 32).** Army "changed since previous publication" markers `*` (single) and `**` (double) prefix glossary terms. The current term-validator never strips them, so `*field` becomes a distinct term from `field`. FM 3-34 confirmed in v0.2.0 candidate-output by `tests/test_batch1_reconciled.py:15-16`.
3. **Same-page Section I tail / Section II header residue (CHANGELOG.md line 31).** Unit 3's range narrowing is page-granular: when one page contains both Section I tail and Section II header, the page-level filter passes the whole page through. ~15% residue on AR 380-381 page 88 (~6/40 entries).
4. **Bold-rate measured on full glossary range, fallback runs on narrowed range** (`src/fedresearch_dictionary_extractor/core/analyzer.py:87-100`). Decisions are made on different denominators. Trivial inconsistency from the Unit 3 refactor.
5. **`extraction_timestamp` in JSON output** (`src/fedresearch_dictionary_extractor/core/analyzer.py:116`). Output is not byte-identical for the same input PDF; backend cannot use the output as a cache key. Backend currently strips `extraction_timestamp` in its candidate-output regen script (per `2026-04-26-v0.2.0-release.md` §3.2), but the field still exists in production output and prevents broader determinism.
6. **Test contracts for orthogonal-bug-class survivals are buried in module docstrings** (`tests/test_batch1_reconciled.py:6-26`). Bare `assert in actual` makes inadvertent fixes look like test failures rather than triggering loud XPASS signals.
7. **`pdfplumber>=0.11.0` declared but unused** (Phase 0 audit `grep -rn pdfplumber src/ tests/` found references only in auto-generated `egg-info/` files). Unnecessary transitive dep + CVE surface.

**Live downstream impact (Phase 0 audit, 2026-04-27):** the FedResearch backend's `definitions` table holds 21,594 stale `army-v1.0.0` rows alongside 6,087 `army-v2.0.0` rows across 847 documents (a separate idempotency bug — addressed by PR-B). The v0.3.0 wheel + EXTRACTOR_VERSION bump in PR-A-pin will trigger another full re-extraction wave; PR-B's GC fix will clean up both v1.0.0 and v2.0.0 stale rows in the same transaction.

## 2. Verified context (Phase 0, 2026-04-27)

| Item | Evidence |
|---|---|
| Current wheel version | `pyproject.toml:7` → `version = "0.2.0"`; `src/fedresearch_dictionary_extractor/__init__.py:6` → `__version__ = "0.2.0"`; Hetzner `extract-definitions --version` → `0.2.0` |
| Backend EXTRACTOR_VERSION constant | `apps/backend/src/definition-extraction/extraction-worker.service.ts:60` → `const EXTRACTOR_VERSION = "army-v2.0.0";` |
| Backend wheel pin | `apps/backend/Dockerfile:96-97` → URL `v0.2.0/...whl` + SHA `8e5a1fb3d5712772669dc18eb2f737f9da55ae5d63339430e8cbf3bff0502d5e` |
| Inline extractor module | `src/fedresearch_dictionary_extractor/extractors/inline.py` (~96 lines, two `re.compile` patterns at module top, runs on entire PDF per analyzer dispatch) |
| Glossary extractor — term column / classification | `src/fedresearch_dictionary_extractor/extractors/glossary.py` (~694 lines; per-page parsing at lines 314-550; term-style detection ~485-496) |
| Section II narrowing | `src/fedresearch_dictionary_extractor/extractors/glossary.py:215-297` (`narrow_to_section_ii`); call site `src/fedresearch_dictionary_extractor/core/analyzer.py:60-69` |
| Bold preservation rate | `src/fedresearch_dictionary_extractor/core/analyzer.py:87-100` (gate); `:155-182` (helper `_bold_preservation_rate`) |
| `extraction_timestamp` source | `src/fedresearch_dictionary_extractor/core/analyzer.py:116` writes `datetime.now(UTC)` |
| JSON schema | `src/fedresearch_dictionary_extractor/schema/definition-output-v1.json` (additive metadata fields are optional per Unit 3 — no schema bump needed for #5 if the field is omitted, not renamed) |
| Test under modification | `tests/test_batch1_reconciled.py` (3K, lines 1-29 docstring + lines 13-26 forbidden-pair assertions) |
| Validation suite invocation | `pyproject.toml` → `addopts = "-m 'not validation'"`; corpus tests behind `-m validation` |
| pdfplumber usage | `grep -rn 'pdfplumber\|import pdfplumber' src/ tests/` → only `src/fedresearch_dictionary_extractor.egg-info/{PKG-INFO,requires.txt}` (auto-generated, not source) |
| CI workflow | `.github/workflows/ci.yml` builds wheel on push, computes SHA-256 (lines 49-54), uploads as 14-day artifact (line 60); does NOT auto-publish Release |

## 3. Approach (TDD order)

Implementation cadence: each fix gets a failing test first, then minimal implementation to green, then refactor. Fix order chosen so easier groundwork lands first and so XPASS signals from fix #6 catch any inadvertent corrections from later fixes.

### 3.1 Fix #6 — xfail markers on `test_batch1_reconciled.py`

**Goal:** make the orthogonal-bug-class contract loud and explicit. Future fixes that resolve a limitation surface as XPASS rather than passing silently.

**Edit:** `tests/test_batch1_reconciled.py:13-26` — replace bare `assert known_bad_pair in actual` with `pytest.mark.xfail(strict=False, reason="orthogonal bug class — see CHANGELOG.md")` parametrized cases. `strict=False` because PR-A fixes #1 and #2 will resolve two of the three forbidden pairs *in this PR*; the test should XPASS on those two and continue XFAIL on the AR 380-381 same-page residue (deferred to PR-A fix #3, which will then XPASS as well).

**Test:** the file IS the test. Verification = `pytest tests/test_batch1_reconciled.py -v` produces XFAIL/XPASS markers, no FAILED.

**Sequence note:** land #6 BEFORE #1 and #2 so the corrections trigger XPASS (visible signal); landing #6 after #1/#2 would silently pass.

### 3.2 Fix #2 — asterisk-prefix term strip + flag

**Goal:** Army `*field` and `**engineer` markers stripped before classification; `flags: ["changed_since_prior_pub"]` added so downstream consumers can surface provenance.

**Tests (new file `tests/test_asterisk_prefix.py`):**
- Synthetic span fixture with term `*field` → output entry has `term="field"`, `flags` contains `"changed_since_prior_pub"`.
- `**engineer` → `term="engineer"`, same flag (one occurrence is sufficient — both markers map to the same flag).
- Bare `field` (no asterisk) → `flags` does NOT contain the marker.
- Term `*` alone (degenerate) → not extracted (existing invalid-term filter retains).

**Implementation:** in `src/fedresearch_dictionary_extractor/extractors/glossary.py`, find the term-extraction call site (~ line 485-496 per Phase 1 exploration; will verify exact location by grep before editing). Pre-strip leading `*+` from the raw term BEFORE the invalid-term filter and BEFORE `normalize.normalize_term()`. Append `"changed_since_prior_pub"` to the entry's `flags` list when stripping occurred.

**Open decision (resolve during impl):** strip in `glossary.py` or in `normalize.py`? Decision criterion: the flag must be set on the *entry*, not on the normalized form. So the strip + flag-emission must live where the entry dict is assembled (glossary.py); `normalize.py` cannot emit flags. Strip happens in glossary.py.

**Corpus impact:** PR description must include `validation_set/candidate-output/` diff for FM 3-34 and any other doc with `*`-prefixed terms.

### 3.3 Fix #1 — inline regex sentence-boundary anchoring

**Goal:** TC 1-19.30 `dampen \nusually` page-102 fragment NOT extracted; all known-good `For purposes of… X means Y` definitions still extracted.

**Tests (new file `tests/test_inline_anchoring.py`):**
- Negative: synthetic body-text fragment matching the current too-loose pattern → not extracted.
- Negative: TC 1-19.30 page 102 (or a synthetic minimal reproduction) → `dampen` not in output.
- Positive: 3 known-good inline definitions from existing validation corpus → still extracted with same `term`/`definition` shape.

**Implementation:** `src/fedresearch_dictionary_extractor/extractors/inline.py`, the two `re.compile` patterns at the top of the module:
- Add `(?<=[.!?\n])\s+` lookbehind to require sentence-boundary start.
- Tighten the `term` capture group: `\b[A-Z][\w-]{1,40}\b` (capitalized, 2–41 chars). This rejects `dampen` (lowercase first letter from mid-sentence flow).
- Confidence cap (`inline.py:68` = 0.65) unchanged.

**Validation:** `pytest -m validation` corpus diff documented in PR description.

### 3.4 Fix #3 — intra-page Section II boundary filter

**Goal:** when a page contains both Section I tail and Section II header (or Section II tail + Section III header), only the in-Section-II spans are extracted.

**Tests (new file `tests/test_intra_page_boundary.py`):**
- Synthetic two-section-on-one-page span fixture: 5 spans above the "Section II" line (Section I tail) + 5 spans below (Section II body) → only the lower 5 enter the glossary entry pipeline.
- Inverse: 5 spans above the "Section III" line (Section II tail) + 5 below (Section III body) → only the upper 5 are kept.
- No-boundary page (pure Section II body) → all spans pass through (regression guard).

**Implementation:** new helper `_intra_page_boundary_filter(spans, page_index, section_ii_start_page, section_ii_end_page, header_y_by_page) -> list[span]` in `glossary.py`. Called from `core/analyzer.py:60-69` after page-level scoping but before per-page parsing. Uses Y coordinates (already extracted by `glossary.py:314-550` span-grouping). Only fires on the boundary pages (`page == section_ii_start_page` and `page == section_ii_end_page + 1`).

**Risk:** the regex-based header detection in `glossary.py:159-212` returns the page index; need to extend it to also return the header's Y coordinate. Minimal extension — additive return field, internal API.

### 3.5 Fix #4 — bold-rate uses narrowed range

**Goal:** `_bold_preservation_rate()` and the fallback parser measure the same denominator.

**Test (extend `tests/test_section_headers.py` or new minimal test):**
- Synthetic doc where bold rate on the full range is below threshold but above threshold on the narrowed range → fallback should NOT fire (because narrowing fixed the underlying signal).
- Inverse → fallback fires correctly.

**Implementation:** `src/fedresearch_dictionary_extractor/core/analyzer.py:87-100` — currently passes the full glossary `pages` slice to `_bold_preservation_rate()`. Change to pass the narrowed slice (already computed for the fallback parser, line 96 per Phase 1). Pure refactor; no threshold change.

### 3.6 Fix #5 — `--deterministic` CLI flag

**Goal:** with `--deterministic`, two consecutive runs against the same input PDF produce byte-identical output JSON.

**Tests (new file `tests/test_deterministic_flag.py`):**
- Run the CLI subprocess against a small fixture PDF twice with `--deterministic --output a.json` then `--output b.json`; assert `Path("a.json").read_bytes() == Path("b.json").read_bytes()`.
- Without the flag (default behavior), `extraction_timestamp` differs across runs (negative regression guard).

**Implementation:**
- `src/fedresearch_dictionary_extractor/cli.py` — add `--deterministic` argument, default `False`, pass through to the analyzer.
- `src/fedresearch_dictionary_extractor/core/analyzer.py:116` — when deterministic, omit `extraction_timestamp` from the metadata dict; also audit for any other wall-clock or PID fields and exclude them.
- Schema (`src/fedresearch_dictionary_extractor/schema/definition-output-v1.json`) — `extraction_timestamp` must already be optional (verify with `grep -nE "extraction_timestamp" src/fedresearch_dictionary_extractor/schema/`); if it's marked required, mark optional in this PR (additive, schema_version stays `"1"`).

**Backend coupling (out of scope, lives in PR-C):** PR-C's backend changes will invoke `extract-definitions --deterministic` from the worker subprocess. PR-A only ships the flag.

### 3.7 Fix #16 — drop unused `pdfplumber` dep

**Goal:** smaller wheel surface, fewer transitive CVEs.

**Implementation:**
- `pyproject.toml` — remove `pdfplumber>=0.11.0` from `[project.dependencies]`.
- Re-run `uv pip install -e ".[dev]"` and full test suite to confirm no transitive breakage.
- Regenerate `egg-info/` artifacts (or let them auto-regen on next `pip install -e`).

**No new tests** — existing 163-test suite is the regression detector.

### 3.8 Version + CHANGELOG

After all six fixes green:
- `pyproject.toml:7` → `version = "0.3.0"`
- `src/fedresearch_dictionary_extractor/__init__.py:6` → `__version__ = "0.3.0"`
- `CHANGELOG.md` — new `[0.3.0]` section listing the seven fixes + reaffirming deferred limitations (per the established v0.2.0 pattern at `2026-04-26-v0.2.0-release.md` §3.8).

### 3.9 Commit + PR + tag + GitHub Release

- One commit per fix (atomic), in TDD order. Final commit: version bump + CHANGELOG.
- Open PR against `main`. CI runs unit tests + builds wheel + computes SHA-256.
- After merge: `git tag v0.3.0 main && git push --tags`. Manually create GitHub Release `v0.3.0`, attach the CI-built wheel, paste SHA-256.
- Capture wheel URL + SHA-256 for PR-A-pin (companion backend PR).

## 4. Assumptions & alternatives

**Assumption A1:** the term-extraction site at `glossary.py` ~485-496 is still load-bearing for fix #2. Verify via grep before editing; if the line numbers have drifted, the grep targets `term-style spans collection` regardless.

**Assumption A2:** `extraction_timestamp` is the only wall-clock field in the JSON output. Verify via `grep -nE "datetime\.now|time\.time|uuid\." src/`. If others exist (UUIDs, PIDs), include them in the deterministic strip.

**Assumption A3:** the existing inline regex's true-positive set is fully covered by the validation corpus. If post-fix #1 the corpus shows lost positives, tighten the regex less aggressively (relax the capitalized-noun-phrase requirement to allow lowercase abbreviations like `eg`).

**Alternative considered for #5:** moving `extraction_timestamp` into a separate `diagnostics` sub-object (always emitted) rather than gating via a flag. Rejected — flag is more explicit, additive, and matches the v0.2.0 candidate-output regen script's existing strip-then-compare workflow (`2026-04-26-v0.2.0-release.md` §3.2). The flag also lets local debugging keep timestamps without affecting backend cache discipline.

**Alternative considered for #2:** mark `*field` as a synonym of `field` rather than stripping. Rejected — the asterisk is a temporal-revision marker (per Army Pubs convention), not a semantic distinction. Stripping + flag preserves provenance without polluting the term key.

## 5. The hard 30%

| Risk | Why it's hard | Mitigation |
|---|---|---|
| #1 inline regex too tight loses true positives | Inline definitions in body text use varied capitalization; `\b[A-Z][\w-]{1,40}\b` may reject legitimate `IED means improvised explosive device` patterns | TDD: test against the existing validation corpus's positive set BEFORE merging; if any positives lost, relax the upper bound case constraint or add an acronym carve-out |
| #2 asterisk strip mis-fires on legitimate `*` content | If any glossary term legitimately contains `*` mid-string (math operators, regex examples), the leading-only strip should be safe — but Section II of an Army pub on cryptography could surprise us | Strip ONLY leading `*+`, never internal; xfail/skip any validation-corpus doc that has internal `*` in glossary terms (none found in current corpus per Phase 1) |
| #3 intra-page filter requires Y-coordinate plumbing through the regex match path | The current `_section_ii_header_match()` returns page index only; need to also return Y. Risk of breaking the existing return-shape contract | Add Y as an optional second return value (tuple-extension) or new field on a return dataclass; keep existing call sites working |
| #5 deterministic flag silently drops a field downstream consumers depend on | If anything downstream relies on `extraction_timestamp` being present in JSON when the backend invokes it (post-PR-C), removing the field could break parse code | PR-C's backend parser MUST treat `extraction_timestamp` as optional already (it's optional in the schema). Confirm via grep in the FedResearch repo before PR-C lands |
| Six fixes in one PR creates a large diff | Reviewability suffers; bisect-debugging gets harder if a regression appears | One commit per fix, atomic; PR description has a per-fix verification checklist; if review surfaces concerns, split into PR-A1 / PR-A2 |

## 6. Blast radius

**Files modified (this PR):**
- `pyproject.toml` (version + dep removal)
- `CHANGELOG.md` (new section)
- `src/fedresearch_dictionary_extractor/__init__.py` (`__version__`)
- `src/fedresearch_dictionary_extractor/cli.py` (new `--deterministic` arg)
- `src/fedresearch_dictionary_extractor/extractors/inline.py` (regex tightening)
- `src/fedresearch_dictionary_extractor/extractors/glossary.py` (asterisk strip, intra-page filter helper, header-Y plumbing)
- `src/fedresearch_dictionary_extractor/core/analyzer.py` (intra-page filter call site, bold-rate range alignment, deterministic timestamp gating)
- `src/fedresearch_dictionary_extractor/schema/definition-output-v1.json` (only if `extraction_timestamp` is currently `required`)

**Files added:**
- `tests/test_asterisk_prefix.py`
- `tests/test_inline_anchoring.py`
- `tests/test_intra_page_boundary.py`
- `tests/test_deterministic_flag.py`

**Files modified (tests):**
- `tests/test_batch1_reconciled.py` (xfail markers)

**Validation corpus impact:** `validation_set/candidate-output/` JSONs change for any doc with inline matches, asterisk-prefix terms, or same-page Section II/I residue. Diff documented in PR description; no commits to candidate-output in this PR (handled by the next corpus-refresh task post-merge, mirroring the v0.2.0 pattern).

**Downstream coupling:**
- `fedresearch` repo PR-A-pin (`feat/2026-04-27/dict-wheel-v0.3.0-pin`) MUST merge in lockstep (same day) to bump `EXTRACTOR_VERSION` and trigger re-extraction of all 1638 SUCCEEDED queue rows.
- PR-C's backend changes consume the new `--deterministic` flag (default off in PR-A — no immediate backend effect).

**Reversibility:** full git revert restores prior behavior. No data migrations. No GCS/S3 state mutation.

## 7. Verification

**Pre-merge:**
- `pytest -q` (default exclusion of `validation` mark) → all green; xfail/xpass markers visible.
- `pytest -m validation` → all green; corpus diff documented in PR description.
- `python -m build` → wheel produced; `pip install dist/*.whl` in clean venv works.
- `extract-definitions --version` → `0.3.0`.
- `extract-definitions --deterministic --input <fixture.pdf> --output a.json && extract-definitions --deterministic --input <fixture.pdf> --output b.json && diff a.json b.json` → empty diff.
- `extract-definitions --input <fixture.pdf> --output c.json` (no flag) → contains `extraction_timestamp` (back-compat regression guard).

**Post-merge (handed off to PR-A-pin):**
- GitHub Release `v0.3.0` published with wheel + SHA-256 documented.
- PR-A-pin updates `apps/backend/Dockerfile` URL + SHA AND `extraction-worker.service.ts:60` constant in lockstep.

## 8. Documentation impact

- `CHANGELOG.md` — new `[0.3.0]` section.
- `README.md` — no changes (CLI surface additive only).
- `docs/` — no existing docs in this repo reference the inline regex or asterisk handling at the level of detail this PR changes; no doc updates required here.
- `docs/ops/extraction-worker.md` (in `fedresearch` repo) — handled by PR-A-pin (coordination table update + re-extraction blast radius note).

## 9. Completion criteria

- [ ] All seven fixes implemented per §3, each as an atomic commit in TDD order.
- [ ] `pytest -q` green on default (unit) suite.
- [ ] `pytest -m validation` green on corpus suite; diff documented in PR description.
- [ ] `pyproject.toml` and `__init__.py` bumped to `0.3.0`.
- [ ] `CHANGELOG.md` `[0.3.0]` section lists seven fixes + reaffirms deferred limitations.
- [ ] `pdfplumber` removed from `pyproject.toml`; egg-info regenerates clean.
- [ ] `--deterministic` flag produces byte-identical JSON across two runs against the same fixture PDF.
- [ ] PR opened against `main`; CI green; wheel artifact built with documented SHA-256.
- [ ] After merge: `git tag v0.3.0 && git push --tags`; GitHub Release published with wheel + SHA-256.
- [ ] PR-A-pin opened in `fedresearch` repo with the new wheel URL + SHA + `EXTRACTOR_VERSION` bump to `army-v2.1.0`.
