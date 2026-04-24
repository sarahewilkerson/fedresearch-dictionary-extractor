# Plan: Auto-classifier tightening (Option B only)

**Date:** 2026-04-24
**Repo:** `/Users/mw/code/fedresearch-dictionary-extractor`
**Branch (proposed):** `feat/2026-04-24-classifier-tightening`
**Parent context:** PR1.2-quality post-ship + PR4.0 shipped. User picked Options B + D from the auto-classifier menu.
**Successor:** Option D (LLM-judge) gets a separate plan + /develop cycle — see §7 for scope.

## Iter-1 split decision (rationale)

Initial plan bundled B (classifier tightening) + D (LLM-judge with new dep, secrets, prompt safety, cache). Codex iter-1 flagged this as two distinct approval surfaces with different risk axes. Per CLAUDE.md "iter-1 architectural finding → consider split" (same pattern applied successfully in PR4 → PR4.0+PR4.1):

- **This plan (Option B):** classifier rule fixes in `scripts/build_labels_yaml.py` + committed regression oracle + extracted testable module. No new deps, no network, no secrets. ~3 hours.
- **Option D plan (separate):** `scripts/llm_judge.py` with `anthropic` SDK, prompt-injection guards, retry/backoff, cost caps, response-contract validation, mocked unit tests, committed API-response fixture. All 4 D-specific Codex findings baked in upfront.

## Phase 0.a Classification

**fast-path-eligible** — single-file classifier tightening + module refactor + unit tests. No production code. No Dockerfile. No new deps. No security-sensitive paths. Revertable via single `git revert`.

## Context

Stage-2 labeling (PR1.2) produced a working classifier but required 12 user overrides via `FLIPS_BAD_TO_GOOD` / `FLIPS_GOOD_TO_BAD` in `scripts/build_labels_yaml.py`. The overrides cluster around three misclassification patterns:

1. **≥9-word terms with parenthetical suffix get rejected.** Real long glossary entries like `Medical treatment facility basic daily food allowance (MTF BDFA)`, `Pharmaceutical care (Academy of Managed Care Pharmacy's Concepts in Managed Care Pharmacy series)`, `Pharmacy data transaction service (PDTS) (from PDTS Business Rules)` (note: two paren groups), `Standard study number–line item number automated management and integrating system` — all hit `len(words) > 8` in `looks_like_noun_phrase` and get flagged `[b]`.

2. **Digit-prefix abbreviations rejected by alpha-ratio gate.** `1LT` / `2LT` / `1SG` have alpha-ratio ~0.67 < 0.85 threshold → rejected despite being real military-rank abbreviation entries.

3. **Short-def abbreviations rejected by `len(d) < 15` gate.** `vol` → `voluntary` (9-char def) is a real abbreviation; gate drops it.

Root cause: each rule was individually conservative, but composed they reject legitimate Army-glossary patterns. Fix: tighten rule semantics (not relax them globally).

## 1. Files modified

- **NEW** `src/fedresearch_dictionary_extractor/labels_classifier.py` — classifier helpers extracted from `scripts/build_labels_yaml.py`. Importable library module, no top-level side effects. Addresses Codex iter-1 #4.
- `scripts/build_labels_yaml.py` — imports classifier from the new module; retains script-specific wiring (BATCH lists, FLIPS dicts, YAML writer).
- **NEW** `tests/test_labels_classifier.py` — unit tests against the library module (not the script). Covers all three fix patterns + existing override cases + negative examples.
- **NEW** `validation_set/classifier_snapshot.yaml` — committed snapshot of classifier output over the checked-in `candidate-output/*.json` corpus. Addresses Codex iter-1 #2 (reviewable regression oracle).
- **NEW** `scripts/refresh_classifier_snapshot.py` — tiny script that regenerates `classifier_snapshot.yaml`. Called before commits that touch the classifier so the snapshot diff is visible in PR review.

### Import contract (Codex iter-2 #1 + iter-3 #1)

`scripts/build_labels_yaml.py` is a dev tool that imports both `yaml` (from PyYAML) and `fedresearch_dictionary_extractor.labels_classifier`. PyYAML lives in `[project.optional-dependencies].dev` per `pyproject.toml`, so the correct install is `pip install -e '.[dev]'` (editable + dev extras).

**Verification gate — two smaller checks instead of one brittle script-entrypoint probe (Codex iter-3 #1 + iter-4 #3 — uses `python3` which is on PATH; NO Makefile reference):**

1. **Import-only smoke (module contract):**
   ```bash
   python3 -m venv /tmp/vfresh \
     && /tmp/vfresh/bin/pip install --quiet -e '.[dev]' \
     && /tmp/vfresh/bin/python -c "from fedresearch_dictionary_extractor.labels_classifier import classify; assert classify('Active duty', 'Full-time military service of the United States.') == 'g'; print('IMPORT CONTRACT: PASS')"
   ```
   Confirms the module is importable from a fresh install + a basic classify call works. No script side-effects.

2. **Script-entrypoint smoke (realistic invocation):**
   ```bash
   /tmp/vfresh/bin/python scripts/build_labels_yaml.py \
     && test -f validation_set/labels.yaml \
     && echo "SCRIPT ENTRYPOINT: PASS"
   # Rollback: restore repo-pinned labels.yaml (gitignored but may exist locally)
   ```
   Runs the actual dev-tool path; asserts exit 0 and `validation_set/labels.yaml` file is created.

Both gates run in §6 step 2 (right after the extraction refactor, before any Option B fixes land). Script is `scripts/verify_classifier_module.sh` (committed); runs both checks. NO Makefile (repo has none — Codex iter-4 #3).

## 2. Option B fixes (specified concretely)

### 2a. Parenthetical-suffix noun phrases (fixes MTF BDFA, PDTS, etc.)

Algorithm (Codex iter-1 #3 — specified precisely, handles multiple trailing paren groups):

```python
_TRAILING_PAREN_RE = re.compile(r"\s*\([^()]{1,120}\)\s*$")

def _strip_trailing_parens(t: str, max_strips: int = 3) -> str:
    """Strip up to max_strips balanced trailing '( ... )' groups, one at a time.
    Handles 'Pharmacy data transaction service (PDTS) (from PDTS Business Rules)'
    by peeling the rightmost paren first, then the next, etc."""
    current = t.rstrip()
    for _ in range(max_strips):
        stripped = _TRAILING_PAREN_RE.sub("", current)
        if stripped == current:
            break
        current = stripped.rstrip()
    return current

def looks_like_noun_phrase(t: str) -> bool:
    core = _strip_trailing_parens(t)
    words = core.split()
    if not words or len(words) > 10:  # was 8; allow 10-word medical/tech phrases
        return False
    if re.search(r"\.\s+\S", core):
        return False
    if words[-1].lower().rstrip(".,;:") in STOP_TAIL:
        return False
    if sum(1 for c in core if c.isalpha() or c.isspace() or c in "-/") / max(len(core), 1) < 0.85:
        return False
    return True
```

Stopping conditions (explicit per Codex iter-1 #3):
- At most 3 strip passes (handles PDTS 2-paren case, guards against pathological inputs)
- Paren group must be balanced flat (`[^()]` inside) — nested parens NOT handled; term is rejected as non-noun-phrase
- Paren content length 1-120 chars (catches normal acronym/citation, rejects paragraph-in-parens)
- Core (post-strip) uses the 10-word limit + existing alpha-ratio check

### 2b. Digit-prefix abbreviations (fixes 1LT, 2LT, 1SG only)

**Codex iter-2 #5 fix — narrow to observed shape:** exactly 1 digit + 2-3 letters. Excludes MOS codes like `11B` (2 digits) and ambiguous patterns.

```python
_DIGIT_PREFIX_ABBREV_RE = re.compile(r"^\d[A-Z]{2,3}$")

def is_digit_prefix_abbrev(term: str, definition: str) -> bool:
    """Matches military rank abbreviations: 1LT, 2LT, 3LT, 1SG, 2SG.
    Intentionally NOT matching MOS codes (11B, 13F, 25U) which start with 2 digits
    and are not typical glossary-entry shapes in Army doctrine publications."""
    if not _DIGIT_PREFIX_ABBREV_RE.match(term): return False
    if not definition or len(definition.strip()) < 3: return False
    return True
```

Called in `classify()` after `is_recognized_acronym_entry`. Returns `g` on match.

Negative test cases (must reject):
- `11B` (MOS code — 2 digits)
- `99ZZZ` (3 letters + bogus)
- `1` (too short)
- `1A` (1 letter, too short)

### 2c. Short-def abbreviations (fixes vol → voluntary only)

**Codex iter-2 #5 fix — narrow to lowercase-shape observed in Army regs.** Uppercase-start acronyms are already handled by `is_recognized_acronym_entry`; this rule targets lowercase-entry-with-lowercase-expansion cases only.

```python
# In classify(), replace:
if len(d) < 15: return "b"
# With:
if len(d) < 15:
    # Allow short defs for LOWERCASE abbreviation-shape terms:
    # 2-5 lowercase letters in term, def is lowercase noun phrase 3-50 chars.
    # Explicitly targets "vol" -> "voluntary" pattern. Uppercase-start
    # acronyms go through is_recognized_acronym_entry above.
    if re.match(r"^[a-z]{2,5}$", t) and re.match(r"^[a-z][a-z ]{2,49}$", d):
        return "g"
    return "b"
```

Negative test cases (must reject despite short def):
- `Car` / `automobile` — term starts uppercase → fails `^[a-z]` → `b` (also: unlikely Army term)
- `ration` / `.` — def < 3 chars → fails → `b`
- `abcdef` (6 chars) / `xyz` — term too long → fails → `b`
- `word` / `Word.` — def starts uppercase → fails → `b`

### 2d. Dead-code cleanup + comments

- Leave `re.fullmatch(r"[A-Z]{6,}", t)` in place; add a comment explaining it's only reached when `is_recognized_acronym_entry` fails (def starts non-alpha or < 3 chars — actual garbage like `UNCLASSIFIED / PIN-only`).
- Update the module docstring in the new `labels_classifier.py` to note the 2a/2b/2c rules.

## 3. Committed regression oracle — TWO snapshot files (Codex iter-1 #2 + iter-2 #3 + iter-4 #2)

**Codex iter-4 #2 fix:** plan now commits TWO snapshot files, one immutable pre-fix baseline that survives past step 5, and one "current" snapshot that reflects latest classifier state.

- `validation_set/classifier_snapshot_prefix.yaml` — committed ONCE in step 3, never overwritten. Represents pre-fix classifier behavior. Used as the before-state for regression tests.
- `validation_set/classifier_snapshot.yaml` — current classifier verdicts. Overwritten each time the classifier changes. Pre-fix content matches `_prefix.yaml` at step 3; post-fix content reflects Option B at step 5.

Both files are deterministic (no `generated_at` timestamp per iter-2 #3). The only metadata is `classifier_version` + `candidate_corpus_hash`.

```yaml
# Deterministic snapshot of classify() verdicts over validation_set/candidate-output/.
# Regenerate via: python scripts/refresh_classifier_snapshot.py
# DO NOT hand-edit.
#
# Reviewers inspect the diff: unexpected flips are the signal.
# No timestamps — the file is bit-for-bit stable when inputs and classifier are unchanged.
classifier_version: v2-2026-04-24
candidate_corpus_hash: sha256:...   # SHA-256 of sorted(candidate-output/*.json) contents
entries:
  - pdf: AR_600-20.pdf
    verdicts:
      - term: "Active duty"
        source_type: glossary
        verdict: g
      - term: "Active status"
        source_type: glossary
        verdict: g
      # ... all entries, sorted by pdf + term
```

**How it works:**
- `scripts/refresh_classifier_snapshot.py` reads every `validation_set/candidate-output/*.json`, runs `classify()`, writes the snapshot YAML in deterministic order (sorted pdf filename, sorted term).
- Committed. When Option B's changes land, `git diff validation_set/classifier_snapshot.yaml` shows ONLY verdict flips (no timestamp churn).
- Baseline snapshot committed in step 3 of §6 (pre-fix state). Option B changes land in step 4. New snapshot in step 5. Diff in PR review shows exactly the 12 expected flips (§5a).

## 4. Hard 30%

- **Parens-suffix stripping edge cases.** Worst-case inputs with 4+ paren groups or mismatched parens get partial strip and may slip through. Mitigation: `max_strips=3` bounds the loop; balanced-flat constraint `[^()]` rejects nested.
- **Digit-prefix regex breadth.** `\d{1,2}[A-Z]{2,4}` admits things like `99ZZZZ` (nonsense). Relying on the short-def rule + flipped `NOISE_TERMS` for backup. Acceptable given rarity.
- **Short-def abbrev rule** could admit a short noun like `car` / `dog` as terms if def is also a noun phrase. Unlikely in Army glossaries. Watch for false positives in the snapshot diff.
- **Classifier snapshot drift.** If nobody regenerates the snapshot before committing classifier changes, the committed snapshot goes stale. Mitigation: document the refresh step in §6 execution sequence + in PR description.
- **Regression on existing user overrides.** Example: if Option B now classifies an overridden term correctly, the override becomes redundant (harmless). If Option B newly misclassifies a Tier-1 positive, regression. Caught by pytest + snapshot diff.

## 5. Verification

| Gate | Threshold | Source |
|------|-----------|--------|
| `pytest tests/test_labels_classifier.py` | all pass | new unit tests |
| `pytest tests/` (existing suite) | 40/40 still pass | regression |
| `pytest -m validation` | Tier-1 100% recall, 0 neg violations (Option B must not regress `labels.yaml`) | validation harness |
| `ruff check src/ tests/ scripts/` | clean | lint |
| Classifier snapshot diff | only intended flips visible (the 12 previously-overridden terms go g→g, currently-bad terms stay b) | `git diff validation_set/classifier_snapshot.yaml` in the PR |
| No top-level side effects in `labels_classifier.py` | `python -c "import fedresearch_dictionary_extractor.labels_classifier"` exits 0 without doing I/O | manual smoke |

### 5a. Expected flip list — committed fixture survives override prune (Codex iter-4 #1)

Option B's fixes must flip EXACTLY the 12 terms from classifier verdict `b` → `g`. No other entries change verdict.

**Codex iter-4 #1 fix — the expected-flip set lives in its OWN committed fixture, independent of `FLIPS_BAD_TO_GOOD`.** When Option B ships + prunes `FLIPS_BAD_TO_GOOD` to empty, the test's source of truth remains intact.

New fixture `tests/fixtures/option_b_expected_flips.yaml` (committed, keyed by exactly `(pdf, source_type, term)`):

```yaml
# Terms that Option B's classifier fixes MUST flip from verdict 'b' to 'g'.
# Independent of scripts/build_labels_yaml.py's FLIPS_BAD_TO_GOOD dict (which
# gets pruned in the same PR). Test sources its truth here.
#
# Each term is looked up in validation_set/candidate-output/*.json by
# (pdf, source_type, term) to get the definition text for classify().
expected_flips:
  - pdf_prefix: AR_40-3
    source_type: glossary
    term: "Medical treatment facility basic daily food allowance (MTF BDFA)"
    rule: "2a-parens-suffix"
  - pdf_prefix: AR_40-3
    source_type: glossary
    term: "Pharmaceutical care (Academy of Managed Care Pharmacy’s Concepts in Managed Care Pharmacy series)"
    rule: "2a"
  - pdf_prefix: AR_40-3
    source_type: glossary
    term: "Pharmacy data transaction service (PDTS) (from PDTS Business Rules)"
    rule: "2a-multi-paren"
  # ... (all 12; term strings use ’ for curly apostrophe so YAML load
  # matches the corpus bytes exactly)
```

At test-build time, the fixture is regenerated by `scripts/refresh_option_b_fixture.py` (one-shot script) which pulls terms from the current `FLIPS_BAD_TO_GOOD` + verifies each is present in candidate-output JSONs. After step 3 (fixture committed), `FLIPS_BAD_TO_GOOD` can be pruned without affecting the test.

```python
# tests/test_labels_classifier.py
import json, pathlib, yaml
from fedresearch_dictionary_extractor.labels_classifier import classify

FIXTURE = pathlib.Path("tests/fixtures/option_b_expected_flips.yaml")
CAND_DIR = pathlib.Path("validation_set/candidate-output")

def test_expected_flips_classify_good():
    """Each term in the committed fixture must naturally classify as 'g'."""
    fixture = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    for flip in fixture["expected_flips"]:
        json_path = next(CAND_DIR.glob(f'{flip["pdf_prefix"]}*.json'))
        entries = json.loads(json_path.read_text(encoding="utf-8"))["entries"]
        matched = [e for e in entries
                   if e["term"] == flip["term"] and e["source_type"] == flip["source_type"]]
        assert matched, f"fixture term not found in corpus: {flip}"
        assert classify(flip["term"], matched[0]["definition"]) == "g", \
            f"Option B expected to classify as 'g': {flip}"
```

### 5b. FLIPS_BAD_TO_GOOD pruning (Codex iter-2 #4)

After Option B ships and the 12 entries naturally classify as `g`, the `FLIPS_BAD_TO_GOOD` override dict is redundant. **In the same PR**, prune it to empty (keep the dict + a comment noting it's intentionally empty post-Option-B, available for future overrides). A test `test_flips_bad_to_good_is_empty_after_option_b` asserts this to prevent regression drift.

## 6. Execution sequence

1. **Plan committed** (this doc on branch)
2. **Extract classifier to `src/fedresearch_dictionary_extractor/labels_classifier.py`** — pure move, same behavior. Update `scripts/build_labels_yaml.py` imports. Add `scripts/verify_classifier_module.sh` (both fresh-venv gates). Run: bit-for-bit `labels.yaml` diff before/after; `bash scripts/verify_classifier_module.sh` exits 0 with both PASS markers. Commit only if both pass.
3. **Commit BOTH pre-fix snapshots + the expected-flip fixture** (Codex iter-4 #1 + #2):
   - Add `scripts/refresh_classifier_snapshot.py` + generate `validation_set/classifier_snapshot.yaml` on `main`-era classifier.
   - Copy the same content to `validation_set/classifier_snapshot_prefix.yaml` (immutable baseline).
   - Add `scripts/refresh_option_b_fixture.py` + generate `tests/fixtures/option_b_expected_flips.yaml` from the current `FLIPS_BAD_TO_GOOD` + corpus JSONs (validates each term is present).
   - Commit all three.
4. **Apply Option B fixes** (2a + 2b + 2c + 2d) in `labels_classifier.py`. Commit.
5. **Regenerate `validation_set/classifier_snapshot.yaml` only** (NOT `_prefix.yaml`, which stays immutable). Diff must show EXACTLY the 12 flips listed in the fixture. Commit.
6. **Prune `FLIPS_BAD_TO_GOOD` to empty** in `scripts/build_labels_yaml.py`.
   **Semantic-preservation gate (Codex iter-3 #2):** save current `validation_set/labels.yaml` to `/tmp/labels-before-prune.yaml`. Apply prune. Regenerate `labels.yaml`. Diff must be **zero bytes** — prune + natural-g cancel exactly. Any non-zero diff is a bug. Fail-hard: do NOT commit if diff is non-empty.
   Also re-run Tier-1 oracle as a second gate.
   Commit.
7. **Unit tests** in `tests/test_labels_classifier.py`:
   - `test_expected_flips_classify_good`: reads `tests/fixtures/option_b_expected_flips.yaml` (survives prune — Codex iter-4 #1); asserts each fixture term classifies as `g`
   - `test_no_unexpected_classifier_flips`: compares `validation_set/classifier_snapshot.yaml` (current post-fix) against `validation_set/classifier_snapshot_prefix.yaml` (immutable pre-fix — Codex iter-4 #2); asserts the delta equals exactly the fixture's flip set (no extra verdict changes)
   - Negative: 11B, 99ZZZ, 1, 1A (digit-prefix rejects), Car/automobile, ration/., abcdef/xyz, word/Word (short-def rejects)
   - Import contract: `from fedresearch_dictionary_extractor.labels_classifier import classify` works without triggering I/O
   Commit.
8. **Re-run `pytest -m validation`** — Tier-1 still 100% recall, 0 negative violations.
9. **Push branch + PR**
10. **Merge (admin if CI infra outage per carve-out; standard merge if CI green)**

Each commit independently passes `pytest tests/` (non-validation suite). Snapshot invariants: `classifier_snapshot_prefix.yaml` is immutable post-step-3; `classifier_snapshot.yaml` changes only at step 5.

## 7. Option D — DEFERRED to separate plan

Option D (`scripts/llm_judge.py` with anthropic SDK) has 4 distinct Codex iter-1 findings that need upfront design, not iterative cleanup:

1. **Response-contract validation** — malformed JSON, missing/extra indexes, refusal text, truncation. Must fail closed.
2. **Cache key completeness** — include model + prompt-version + source_type; location not `/tmp/`.
3. **Mocked API tests** — committed fixture input/output pairs, no reliance on live API for CI.
4. **Cost assumptions grounded in real workload** — current corpus is 700 entries, not 866. Preflight estimate based on actual tokenization. Per-run + aggregate caps matching observed corpus sizes.

These will be written into the D plan upfront, not as iter-2/3 revisions. Writing B first gets the regression oracle + extracted classifier module that D will also need.

**After B merges:** new plan `plans/2026-04-XX-classifier-llm-judge.md`, its own /develop cycle, its own /review-plan gate with the 4 findings baked in.

## 8. Blast radius

- **Files modified:** 5 (1 moved, 1 modified, 3 new)
- **Production impact:** NONE. Extractor wheel (`src/fedresearch_dictionary_extractor/extractors/`, `profiles/`, `core/`, `normalize.py`) untouched. PR1.2 v0.1.0 wheel unchanged.
- **New deps:** NONE.
- **Runtime surface:** NONE. Classifier is a dev/validation tool; runs only when someone invokes `scripts/build_labels_yaml.py` or the validation harness.
- **Rollback:** single `git revert`. Classifier snapshot reverts too; no state outside git.

## 9. Documentation impact

- `labels_classifier.py` module docstring — describes the three rule families + rationale
- `scripts/build_labels_yaml.py` — brief note that classifier lives in `labels_classifier` module now
- `validation_set/README.md` — mention the committed `classifier_snapshot.yaml` under "Stage-1 oracle" section
- No README.md (top-level) changes
- No CHANGELOG

## 10. Estimated effort

| Phase | Effort |
|-------|--------|
| Classifier module extraction + existing behavior verification | 45 min |
| Snapshot script + baseline snapshot | 30 min |
| Option B fixes (2a + 2b + 2c + 2d) | 45 min |
| Regenerate snapshot + review diff | 15 min |
| Unit tests | 45 min |
| Validation re-run + lint + push + PR | 30 min |

**Total: ~3.5 hours.** Single PR, single branch, fits in one focused half-day.
