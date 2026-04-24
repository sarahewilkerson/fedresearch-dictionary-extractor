## Phase 0.a Classification

**Classification:** full-flow — code change is small (1 regex pattern, 1 new test) but touches production-critical extractor, updates 2 candidate-output JSONs, 1 classifier-snapshot file, 1 regression-oracle test, and 1 helper script. Exclusion applies (single-file change to production-critical code — the extractor wheel).

---

# Plan: Extractor v0.2.a — AR/FM citation-fragment blocklist

**Date:** 2026-04-24
**Repo:** `/Users/mw/code/fedresearch-dictionary-extractor`
**Branch:** `feat/2026-04-24-invalid-term-blocklist`
**Parent context:** PR1.2 Stage-2 labeling identified 3 bold-source-text noise entries. This PR fixes 2 of them (AR 124 + AR 140 citation fragments) with a narrow, corruption-free change. The third case (`Equip for`, PAM_71-32) is deferred to **v0.2.b** because its fix requires deeper parser work: rejecting the term AND its 50-word accumulated continuation, not just its line. Bundling it here would introduce "coherent-but-wrong" definition corruption on the predecessor term, which is worse than the original noise.

## 1. Problem statement

Two noise entries in committed `validation_set/candidate-output/`:

| PDF | Term | Definition | Why |
|-----|------|-----------|-----|
| `AR_135-100` p77 | `AR 124` | `210)` | Citation fragment from `(AR 135 200 and AR 124-210)`: bold split on "AR 124"; next line `-210)` became its orphan "def" |
| `AR_135-100` p83 | `AR 140` | `111)` | Same pattern: `(AR 140-111)` fragment |

(Third case `Equip for` on PAM_71-32 deferred — see v0.2.b scoping at the end of this doc.)

## 2. Root cause

`ArmyProfile.invalid_term_patterns` has pattern `r"^(AR|FM|ADP|ATP|TC|PAM|TM)\s+\d+[-–]\d+\s*$"` (line 56 of army.py) which rejects FULL hyphenated citations like `AR 124-210`. It does NOT reject pre-hyphen fragments like `AR 124`. Bold extraction occasionally splits citations at the hyphen, producing these orphan fragments as glossary term candidates.

**Structural safety argument for the broader rule** (addresses Codex iter-2 F3): all Army doctrine publications are identified as `<TYPE> <series>-<publication>` (cited: every pattern in `ArmyProfile.publication_patterns` at army.py:18-27 uses `\d+[-–]\d+`). A glossary headword in the shape `<TYPE> <digits>` WITHOUT the hyphen cannot be a legitimate reference in Army doctrine — the publication-series number by itself never identifies a document. Such a term is structurally a fragment. Applying the rule repo-wide across all 8 publication families (AR/FM/ADP/ATP/TC/PAM/TM/DA PAM) is defensible.

## 3. Approach & methodology

### 3a. One new pattern in `ArmyProfile.invalid_term_patterns`

```python
# v0.2.a — bold-extraction fragment. Rejects pre-hyphen citation
# prefixes like "AR 124", "FM 6" that occur when bold markup splits
# on a hyphen in "(AR 124-210)". Structurally invalid: Army doctrine
# always identifies publications as <TYPE> <series>-<publication>.
r"^(AR|FM|ADP|ATP|TC|PAM|TM|DA\s*PAM)\s+\d+\s*$",
```

### 3b. Re-extract candidate PDFs (pipeline trace + clean outcome prediction)

**Pipeline (cited by line number):**
- `_validate_term` returns False at `glossary.py:359-365` → rejected term's `line_text` appends to `current_def_lines` of previous term; no flush.
- On next flush (`_flush` at `glossary.py:503-534`): `current_def_lines` joins → `fix_ocr_spacing` → `strip_citations` (using `ArmyProfile.citation_pattern` at `army.py:101-105`: `\s*\(\s*(?:AR|FM|ADP|ATP|TC|PAM|JP|DA\s*PAM|DA|TM|DoDI|DoDD)\s*\d+[-–—]?\s*\d*[^)]*\)\s*`) → `is_gibberish` gate → emit.

**Predicted outcome for AR cases:** the pre-fix JSON shows:
- AR_135-100 p77 "Entry on duty date" def ends with `... (AR 135 200 and` — an open parenthetical.
- AR_135-100 p77 "AR 124" term + def `210)` (the split-off tail).

After the fix: "AR 124" is rejected, its line ("AR 124") accumulates into "Entry on duty date" def, then next line ("210)") also accumulates (falls through `_validate_term` as a non-term line). Result: "Entry on duty date" def ends with `... (AR 135 200 and AR 124 210)` — a complete parenthetical citation. `strip_citations` matches this (the regex handles multi-number citations via the `[^)]*` interior match) and removes it entirely. Final def: clean text with the parenthetical stripped.

Analogous mechanism for AR 140 on p83.

### 3c. End-to-end pipeline test (addresses Codex iter-2 F2 + iter-3 #1)

Add `tests/test_citation_fragment_pipeline.py`: a durable test that exercises the **REAL reject→accumulate→flush→strip path through the extractor's state machine**, not a `_flush`-only shortcut. The interaction between `_validate_term` returning False (line 359), the accumulator append (line 363), and later flush is the whole safety case — a `_flush`-only test bypasses the critical `_validate_term` handoff.

Test structure: construct a minimal synthetic fitz-compatible page (via pdf bytes generated at test-time, or via a page-span mock structure fed into the real glossary-page-parsing loop in `_extract_from_pages`). The test must exercise line 350-365 of glossary.py (the term-validation branch), not just line 503. If a full synthetic PDF is too complex, the alternative is a controlled integration mock that replaces only the PDF-reading layer but runs the whole term-line-parsing state machine including `_validate_term` and its accumulator branch.

`_flush`-only test is explicitly disallowed as a substitute.

### 3d. Regression-oracle test: explicit REMOVED_SINCE_PREFIX allowlist

The test at `tests/test_labels_classifier.py:229` asserts `set(prefix.keys()) == set(current.keys())`. Change to exact-allowlist delta (addresses Codex iter-1 F2):

```python
REMOVED_SINCE_PREFIX: set[tuple[str, str, str]] = {
    # v0.2.a — AR/FM citation-fragment invalid_term pattern (this PR)
    ("AR_135-100_APPOINTMENT_OF_COMMISSIONED_AND_WARRANT_OFFICERS_OF_THE_ARMY_G-1_1994_09_01_OCR.pdf", "glossary", "AR 124"),
    ("AR_135-100_APPOINTMENT_OF_COMMISSIONED_AND_WARRANT_OFFICERS_OF_THE_ARMY_G-1_1994_09_01_OCR.pdf", "glossary", "AR 140"),
}

def test_no_unexpected_classifier_flips() -> None:
    prefix = _load_snapshot(SNAPSHOT_PREFIX)
    current = _load_snapshot(SNAPSHOT)
    removed = set(prefix.keys()) - set(current.keys())
    added = set(current.keys()) - set(prefix.keys())
    assert removed == REMOVED_SINCE_PREFIX, \
        f"unexpected_removed={removed - REMOVED_SINCE_PREFIX}, " \
        f"missing_removed={REMOVED_SINCE_PREFIX - removed}"
    assert not added, f"unexpected corpus growth requires review: {added}"
    # ... existing flip-set logic; adjust to `current.get(key)` so
    #     REMOVED_SINCE_PREFIX entries don't KeyError.
```

Preserves `classifier_snapshot_prefix.yaml` immutability AND records every removal with its source PR.

### 3e. Machine-checked predecessor-def (addresses Codex iter-2 F5 + iter-3 #2)

**Fixture derivation rule (addresses iter-3 #2 tautology):** the expected text in `tests/fixtures/v0_2_a_predecessor_defs.yaml` is derived INDEPENDENTLY of the new extractor output. Not "copy what the new extractor produces." Instead:

1. Read the PRE-fix `Entry on duty date` definition from the current committed candidate-output JSON.
2. Read the noise entry's `"AR 124"` term + `"210)"` def (the split fragment).
3. Manually compute the expected post-strip text by:
   - Appending `"AR 124 210)"` to the pre-fix def (the accumulate step),
   - Applying the known `strip_citations` regex (army.py:101-105) to the result in a Python REPL, CAPTURING the exact output,
   - Committing that captured string into the fixture.
4. Sanity-check the fixture string passes human review as "cleaner than pre-fix, no corruption."

After re-extraction, test asserts the NEW candidate-output's `Entry on duty date` def == fixture text, byte-equal. If the extractor produces different text, the test FAILS — even if the different text looks coherent. This catches the case Codex warns about: new extractor output that happens to look reasonable but doesn't match the expected transformation.

The fixture is committed BEFORE re-extraction is run (as a hand-derived prediction). Re-extraction must match it.

### 3f-bis. Surviving-entry byte-invariant (addresses Codex iter-3 #3)

In addition to the removed-set assertion (§3f), add a corpus-wide invariant: **every (pdf, source_type, term) that survives must have byte-identical field content pre vs post**, EXCEPT the 2 predecessor entries whose defs legitimately changed (and whose expected new content is in the fixture).

Implementation in `tests/test_v0_2_a_corpus_refresh.py::test_surviving_entries_unchanged`:
- Load pre-fix candidate-output from a one-time snapshot (committed at plan time as `tests/fixtures/v0_2_a_pre_fix_snapshot.json` — a serialized map of entry-key → all-fields).
- Load current candidate-output.
- For each (pdf, st, term) in current:
  - If in `PREDECESSOR_DEFS_FIXTURE.keys()`: def checked by §3e; other fields must still match pre-fix.
  - Else: entire entry (def + section + page + label + confidence + flags) byte-equal to pre-fix.
- Catches silent normalization / whitespace / ordering drifts that only-removed-set checks would miss.

### 3f. Corpus-level removal assertion (Codex iter-2 F3 + iter-3 #4)

Scan all 30 post-fix JSONs, collect the set of entry (pdf, source_type, term) tuples, compare to pre-fix set. Assert:
- Removed-set equals exactly `{(AR_135-100, "AR 124"), (AR_135-100, "AR 140")}`.
- Added-set is empty.

**Raw-candidate rejection audit (addresses iter-3 #4):** the pre-check in execution step 2 runs `_validate_term` against *currently-committed* candidate-output terms. That only catches terms that survived the pre-fix pipeline. The new pattern fires BEFORE output is written and can newly suppress raw bold candidates that never made it to the committed JSONs.

To bound that broader blast radius: during re-extraction (execution step 4), enable an instrumented logging hook in `_validate_term` (temporary, local-only — not committed) that records every (pdf, term) newly rejected by the new pattern that wouldn't have been rejected by the pre-existing patterns. After re-extraction, assert the logged set is exactly `{(AR_135-100, "AR 124"), (AR_135-100, "AR 140")}` — if ANY other raw candidate is rejected, stop and reassess the regex scope.

Implementation: pass a `debug_rejections_log` list into `_extract_from_pages` at test-time, or monkey-patch `_validate_term` with a wrapper during the re-extraction run. Log content committed to `docs/plans/2026-04-24-invalid-term-blocklist-rejection-log.txt` as an execution artifact (gitignored, captured in PR comment).

### 3g. PAM_71-32 byte-invariant (addresses Codex iter-3 #5)

The `Equip for` case is deferred to v0.2.b. The `EXCLUDE_FROM_NEGATIVES["PAM_71-32"]` entry stays LIVE. Re-extraction must NOT alter `validation_set/candidate-output/PAM_71-32_*.json`.

Explicit gate in `tests/test_v0_2_a_corpus_refresh.py::test_pam_71_32_unchanged`: `git diff --stat validation_set/candidate-output/PAM_71-32_*.json origin/main` reports zero changes. Byte-identical.

If PAM_71-32 changes unexpectedly (extractor behavior drift on re-run), this case fails loud — the plan's "Equip for deferred" promise is violated.

### 3h. `EXCLUDE_FROM_NEGATIVES` — remove AR entries only (addresses Codex iter-2 F4)

```python
# After this PR:
EXCLUDE_FROM_NEGATIVES = {
    "PAM_71-32":  ["Equip for"],     # DEFERRED to v0.2.b — parser fix needed
}
# AR_135-100's entries removed: v0.2.a extractor fix now rejects "AR 124"
# and "AR 140" at extraction time; the exclusion is dead code.
```

Consistent across all plan sections. The `Equip for` entry stays populated and LIVE until v0.2.b lands.

### 3i. `classifier_snapshot.yaml` refresh

`python3 scripts/refresh_classifier_snapshot.py` — regenerates from new candidate-output. Expected diff: exactly 2 verdict rows removed (AR 124, AR 140), all else byte-identical. `classifier_snapshot_prefix.yaml` stays untouched.

## 4. The Hard 30%

| Area | Risk | Mitigation |
|------|------|-----------|
| Regex over-matches a future legitimate term | Could a future Army doc use `AR 124` alone as a headword? Structurally impossible per §2 safety argument — series-number-alone never identifies a publication. | Structural argument + corpus-scan gate |
| Any unexpected entry disappears during re-extraction | A random other term could coincidentally match | Corpus-level removal assertion (§3f) — hard-fails if any OTHER (pdf, term) disappears |
| Predecessor-def transformation behaves differently than predicted | `strip_citations` regex might not fully clean the reconstructed parenthetical (multi-word "and" interior, OCR-lost hyphens) | Fixture-based exact-text test (§3e) catches unpredicted output; re-extraction early in exec sequence surfaces this before commit |
| `Equip for` deferral leaves 1/3 noise cases in the corpus | User asked for all 3 | Documented v0.2.b scope at bottom of plan; `EXCLUDE_FROM_NEGATIVES` keeps Tier-1 passing in the interim |
| Future corpus-refresh PRs forget to update `REMOVED_SINCE_PREFIX` | Test will fail loud (exact-set equality both directions) | The exact-assertion IS the guard — no silent drift |

## 5. Blast radius

- **Files modified (5):**
  - `src/fedresearch_dictionary_extractor/profiles/army.py` — 1 regex string + comment
  - `validation_set/candidate-output/AR_135-100_*.json` — 2 entries removed; 2 prev-term defs gain cleaned-post-strip text
  - `validation_set/classifier_snapshot.yaml` — 2 verdict rows removed
  - `scripts/build_labels_yaml.py` — `EXCLUDE_FROM_NEGATIVES` loses AR_135-100 key (Equip for stays)
  - `tests/test_labels_classifier.py` — `test_no_unexpected_classifier_flips` uses explicit allowlist
  - `validation_set/README.md` — one-sentence note on `REMOVED_SINCE_PREFIX` mechanism
- **Files added (3):**
  - `tests/test_army_profile_invalid_term.py` — unit tests for the new pattern
  - `tests/test_citation_fragment_pipeline.py` — pipeline integration test (§3c)
  - `tests/test_v0_2_a_corpus_refresh.py` — predecessor-def exact-text + corpus-level removal assertions (§3e, §3f)
  - `tests/fixtures/v0_2_a_predecessor_defs.yaml` — expected predecessor-def text for byte-equality
- **Files NOT modified (explicit):** `validation_set/classifier_snapshot_prefix.yaml` (immutable), `validation_set/candidate-output/PAM_71-32_*.json` (Equip for deferred), `tests/fixtures/option_b_expected_flips.yaml` (none of 12 terms affected).
- **Wheel consumers:** next rebuild picks up pattern; no prod impact on the already-deployed PR1.2 wheel.
- **Revert:** single `git revert <sha>` restores all files.

## 6. Verification

### Unit tests (profile pattern)

| # | Test | Expected |
|---|------|----------|
| N1 | `_validate_term("AR 124", None, res)` | False |
| N2 | `_validate_term("AR 140", None, res)` | False |
| N3-N10 | Parametrized over AR/FM/ADP/ATP/TC/PAM/TM/DA PAM × `{digits}` sans-hyphen | all False |
| N11 | `_validate_term("AR 124-210", None, res)` | False via *existing* pattern (unchanged) |
| N12 | `_validate_term("Equipment concentration site", None, res)` | True (not a false-positive) |
| N13 | `_validate_term("Equip", None, res)` | True |
| N14 | `_validate_term("AR", None, res)` | True (bare TYPE without digits is allowed — another pattern might handle) |
| N15 | `_validate_term("AR 124-210 Supplement", None, res)` | True (hyphenated + suffix isn't a citation) |

### Pipeline integration test (§3c)

| # | Test | Expected |
|---|------|----------|
| P1 | Reject→accumulate→strip pipeline over synthetic AR-fragment flow | Flushed def matches exact expected cleaned text |

### Corpus integration gates

| Gate | Test | Expected |
|------|------|----------|
| Re-extraction successful | `extract-definitions --input-dir ... --output-dir ... --workers 4` | exit 0, 30 JSONs |
| Corpus-level removal | `test_v0_2_a_corpus_refresh.py::test_removed_keys` | `removed == {(AR_135-100, "AR 124"), (AR_135-100, "AR 140")}`, `added == ∅` |
| Predecessor-def exact text | `test_v0_2_a_corpus_refresh.py::test_predecessor_defs_exact` | byte-equal vs fixture |
| Snapshot refresh | `python3 scripts/refresh_classifier_snapshot.py` + `git diff` | exactly 2 rows removed |
| Regression-oracle (allowlist) | `test_labels_classifier.py::test_no_unexpected_classifier_flips` | green |
| Full suite | `pytest tests/` | green |
| Tier-1 oracle | `python scripts/build_labels_yaml.py` | 100% recall, 0 negatives |
| Lint | `ruff check src/ tests/ scripts/` | clean |

## 7. Documentation impact

- **Inline comment** on new pattern in `army.py`
- **validation_set/README.md** — one sentence under "Regression oracle": "When `tests/test_labels_classifier.py::REMOVED_SINCE_PREFIX` adds an entry, the corresponding JSON entry must have been removed from `validation_set/candidate-output/` in the same PR."
- **No CHANGELOG** — repo doesn't maintain one.

## 8. Completion criteria

1. 1 new pattern in `ArmyProfile.invalid_term_patterns` with comment.
2. Unit tests N1-N15 pass.
3. Pipeline integration test P1 passes.
4. Re-extraction completed; exactly `{AR_135-100 AR 124, AR_135-100 AR 140}` removed from candidate-output. No other entries change.
5. Predecessor-def exact-text test passes (byte-equal to fixture).
6. `classifier_snapshot.yaml` regenerated; exactly 2 rows removed.
7. `classifier_snapshot_prefix.yaml` byte-identical to main.
8. Regression-oracle test with `REMOVED_SINCE_PREFIX = {2 entries}` passes.
9. `EXCLUDE_FROM_NEGATIVES`: AR_135-100 entries removed; `PAM_71-32: ["Equip for"]` retained.
10. `labels.yaml` regen; Tier-1 100% recall, 0 negatives.
11. README note added.
12. `pytest tests/` + `ruff check` all green.
13. Raw-candidate rejection log (§3f) shows exactly the 2 expected AR-fragment tuples — no other terms newly blocked across the 30-PDF corpus.
14. `validation_set/candidate-output/PAM_71-32_*.json` byte-identical to origin/main (§3g).
15. All surviving entries across all 30 JSONs (excluding the 2 predecessor defs whose text legitimately changed) are byte-equal pre vs post (§3f-bis).

## 9. Execution sequence

1. **Commit plan doc.** Checkpoint.
2. **Commit patterns + unit tests (N1-N15)** — RED→GREEN internal for new pattern; regression N11 stays green; negative-space N12-N15 stay green. Test file pre-check simulation: before re-extraction, script tests `_validate_term` against every entry's term in current candidate-output; asserts exactly 2 matches (AR 124, AR 140). If more — stop.
3. **Commit pipeline integration test (P1)** — constructed synthetic flow; runs `_flush` with synthetic input; asserts exact expected cleaned output. Commit.
4. **Pre-compute predecessor-def fixture** — hand-derive expected post-strip text per §3e. Use a Python REPL to run `strip_citations` against the manually-constructed merged def string. Commit `tests/fixtures/v0_2_a_predecessor_defs.yaml` + `tests/fixtures/v0_2_a_pre_fix_snapshot.json` (serialized pre-fix entry map). This commit happens BEFORE re-extraction so the fixture is not tautological.
5. **Re-extract all 30 PDFs with instrumented rejection log** — `.venv/bin/extract-definitions --input-dir validation_set/pdfs --output-dir validation_set/candidate-output --workers 4`, with a monkey-patched `_validate_term` (via a local-only wrapper script in docs/plans/) logging every newly-blocked term. Inspect diff: expect exactly 2 entries removed + 2 predecessor defs match fixture. Inspect rejection log: expect exactly 2 tuples. PAM_71-32 byte-identical.
6. **Commit corpus change + test_v0_2_a_corpus_refresh.py + regression-oracle test update** in ONE commit: updated candidate-output JSONs + new corpus-refresh test file (covers §3e exact-def + §3f removed-set + §3f-bis surviving-invariant + §3g PAM byte-identical) + `REMOVED_SINCE_PREFIX = {2 entries}`. All tests green.
7. **Regenerate classifier_snapshot.yaml** — `python3 scripts/refresh_classifier_snapshot.py`. Commit.
8. **Update `EXCLUDE_FROM_NEGATIVES`** — drop AR_135-100 key only. Regenerate labels.yaml (gitignored), verify Tier-1 100% recall / 0 neg. Commit.
9. **Update README.** Commit.
10. **Full test suite + lint.** Fix if broken.
11. **Push + open PR.**
12. **`/review-execution`** gate.
13. Merge on ✅ CLEAN.

## 10. Estimated effort

| Phase | Effort |
|-------|--------|
| Plan (this doc) | 45 min (3 review iters) |
| Unit tests + pattern | 20 min |
| Pipeline integration test | 30 min |
| Re-extraction + fixture capture + corpus-refresh tests | 30 min |
| Snapshot refresh + oracle update | 15 min |
| EXCLUDE update + labels regen + README | 20 min |
| Full suite + lint + PR | 20 min |

**Total: ~3 hours.** Scope narrower than prior iteration (Equip for deferred to v0.2.b); added durable pipeline-integration + machine-checked predecessor-def tests per Codex F2/F5.

---

## Out of scope → v0.2.b

**`PAM_71-32` `Equip for` case.** Current extractor behavior on rejected terms: accumulate the rejected line into the previous term's definition. For `Equip for`, this would append a 50-word unrelated-prose paragraph to the predecessor term, producing semantic corruption that `strip_citations` cannot clean (no parenthetical wrap).

The v0.2.b fix needs a deeper change to `glossary.py:359-365`: when a term is rejected via `invalid_term_patterns`, the extractor should either:
- (A) **Discard** the rejected line entirely, not accumulate — but this changes behavior for ALL rejections, some of which legitimately should accumulate (e.g., OCR-split terms).
- (B) Extend `_validate_term` with a "reject-and-discard-continuation" flag, marking specific patterns as drop-all-following-non-term-lines until the next valid term appears.

v0.2.b gets its own plan + `/develop` cycle. Until then `EXCLUDE_FROM_NEGATIVES["PAM_71-32"] = ["Equip for"]` keeps the Tier-1 oracle clean.
