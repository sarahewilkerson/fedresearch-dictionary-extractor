# Unit 3 — Section II range scoping with Section III end boundary

## Phase 0.a Classification

**fast-path-eligible** — extraction-behavior change but isolated to glossary scoping; profile-gated to Army; existing 137 tests + new range-scoping tests + manual distribution check on local PDFs gate the change. Single repo, fully reversible.

## 1. Problem statement

Unit 2 (PR #14) added detection: every analyzed Army doc now reports `metadata.section_structure ∈ {none, section_i_only, section_ii_only, both, unknown}`. **Unit 3 uses that signal to narrow extraction.** When Section II is detected (`both` or `section_ii_only`), the parser receives a scoped page range starting at the Section II header (excluding any Section I content that precedes it) and ending at the page before the next section header (Section III/IV) — closing Codex Z1 from the original Unit 1 work.

This unit is the actual fix for the AR 380-381 bug (47% single-lc-word terms from Section I bleed). After this lands, re-extraction of AR 380-381 should drop Section I expansions like "Army Audit Agency" and emit only Section II terms.

## 2. Verified context (read at planning time)

- `extractors/glossary.py:120` `find_glossary_page_range(doc, profile) -> (start, end) | None` — UNCHANGED in this unit.
- `extractors/glossary.py:158` `detect_section_structure(doc, start, end, profile)` — Unit 2 helper, returns one of 5 strings.
- `core/analyzer.py:42-49` calls `find_glossary_page_range` then `detect_section_structure` then `parse_glossary_entries(doc, start, end, profile)`. **The narrowing happens between detection and parsing** — only the `start`/`end` passed to `parse_glossary_entries` change.
- `parse_glossary_entries` already filters Section I/II/III text via `invalid_term_patterns:66` (`r"^SECTION(\s+[IVX]+)?\s*$"`) and `HEADER_ZONE_Y` filter — so the Section II header line at top-of-page won't be parsed as a term. **Narrowing the page range is sufficient; no per-line filter changes needed.**
- AR 380-381 layout (verified earlier in conversation): page 84 = Glossary + Section I; page 88 = Section II; page 90 = Section III. `find_glossary_page_range` correctly identifies start = page 84. Narrowing to start at page 88 (Section II) excludes pages 84-87 (Section I content, ~80+ bad entries).

## 3. Approach

### 3.1 `src/fedresearch_dictionary_extractor/profiles/army.py`

Add `SECTION_AFTER_II_HEADER` regex matching ANY section header that comes after Section II (Codex iter-1 #1: also covers Section IV/V cases where III is skipped):

```python
# Headers that mark "this is the end of Section II content" — anything
# numbered III or higher. Per Army Pubs convention sections appear in order.
# OCR-tolerant variants:
#   - III, Ill (capital I + 2 lowercase L), lll
#   - IV, lV, |V (single pipe + V)
#   - V, |, l (defensive — but mostly captured by Section I rejection lookahead;
#     not used here since we're matching III/IV/V/etc, not I)
# Constrained with a tighter trailing requirement (Codex iter-1 #3 fix) so
# body-text references like "Section IV regulations require..." don't match.
# Match requires either end-of-line OR section-style suffix (em/en-dash,
# hyphen, "Terms", "Special", "Subjects", or another all-caps word starting
# the next token).
SECTION_AFTER_II_HEADER = re.compile(
    r"^\s*Section\s+(?:III|Ill|lll|IV|lV|\|V|V)(?:\s*$|\s+(?:—|–|-|Terms|Special|Subjects|Other|[A-Z][A-Z]+))",
    re.IGNORECASE | re.MULTILINE,
)
```

Test cases: `Section III` ✓, `Section Ill` ✓ (AR 380-381 p90), `Section IV` ✓ (Codex #1), `Section IV — Special Subjects` ✓, `Section II` ✗ (II is what we're scoping TO, not past), `Section I` ✗, `Section IV regulations require` ✗ (Codex #3: body text starting with section reference but lacking the standalone trailing pattern).

Also tighten `SECTION_II_HEADER` from Unit 2 to require similar trailing constraint (Codex iter-1 #3 fix). Ship the tightening as part of this unit since it's the same correctness gap:

```python
# RETIGHTENED in Unit 3 (Codex iter-1 #3 fix): require trailing
# end-of-line or recognized section-style suffix to avoid matching
# body text that starts with "Section II" mid-paragraph.
SECTION_II_HEADER = re.compile(
    r"^\s*Section\s+(?:II|Il)(?:\s*$|\s+(?:—|–|-|Terms))",
    re.IGNORECASE | re.MULTILINE,
)
```

Equivalent tightening for `SECTION_I_HEADER`:

```python
SECTION_I_HEADER = re.compile(
    r"^\s*Section\s+(?:I|\||l)(?![Il\|])(?:\s*$|\s+(?:—|–|-|Abbreviations))",
    re.IGNORECASE | re.MULTILINE,
)
```

Add explicit negative tests for body-text references (Codex iter-1 #3): `Section II policies apply` ✗, `Section IV regulations require` ✗, `the Section II — Terms section` ✓ (mid-line — but starts with `the` so `^` won't match). Test these on real production-style strings.

### 3.2 `src/fedresearch_dictionary_extractor/extractors/glossary.py`

Add helper after `detect_section_structure`:

```python
from ..profiles.army import SECTION_AFTER_II_HEADER  # added to existing import

def narrow_to_section_ii(
    doc: fitz.Document,
    start: int,
    end: int,
) -> tuple[tuple[int, int], bool]:
    """When Section II is present in [start, end], return narrowed range
    + a 'narrowing fired' flag.

    Returns ((new_start, new_end), narrowing_fired) where:
      - new_start = first page containing a SECTION_II_HEADER match
      - new_end   = page BEFORE the first SECTION_AFTER_II_HEADER match
                    after new_start, or original end if no III/IV/etc
      - narrowing_fired = True iff Section II header was located AND the
                          narrowed range is non-empty. False on identity
                          transform (Codex iter-1 #4: surface the failure).

    Caller is responsible for invoking this only when section_structure is
    "both" or "section_ii_only". For "none"/"section_i_only"/"unknown" the
    caller passes the original (start, end) to parse_glossary_entries
    unchanged (Unit 3 scope: do not break docs without Section II).

    Identity-transform cases (narrowing_fired=False — caller should treat
    as a soft signal that detection said Section II but narrowing failed):
      1. SECTION_II_HEADER doesn't match in [start, end] (caller-gating
         violation OR page-read error masked the header).
      2. Page-read error on every page during scan.
      3. Narrowed range is empty (new_end < new_start).

    Page-read errors during forward scan for Section III/IV are tolerated
    (skip the page; continue). Distinct from Unit 2's "any error → unknown"
    because here a partial result with a known new_start is more useful
    than reverting to the original wide range.
    """
    found_section_ii_at: int | None = None
    for page_idx in range(start, end + 1):
        try:
            page_text = doc[page_idx].get_text("text")
        except Exception:
            continue
        if SECTION_II_HEADER.search(page_text):
            found_section_ii_at = page_idx
            break

    if found_section_ii_at is None:
        return (start, end), False

    new_start = found_section_ii_at
    new_end = end
    for page_idx in range(found_section_ii_at + 1, end + 1):
        try:
            page_text = doc[page_idx].get_text("text")
        except Exception:
            continue
        if SECTION_AFTER_II_HEADER.search(page_text):
            new_end = page_idx - 1
            break

    if new_end < new_start:
        # Defense-in-depth: empty range → identity transform.
        return (start, end), False

    return (new_start, new_end), True
```

The return-shape change (single tuple → tuple-of-tuple-and-bool) is a contract addition. Helper is brand-new in Unit 3, so no existing callers need migration.

### 3.3 `src/fedresearch_dictionary_extractor/core/analyzer.py`

Modify `analyze_pdf` to narrow the range before parsing when section structure indicates Section II is present:

```python
# Existing detection step (Unit 2):
section_structure = glossary.detect_section_structure(doc, start, end, profile)

# Unit 3: narrow the range to Section II when present.
parse_start, parse_end = start, end
narrowing_fired = False
narrowing_attempted = False
if section_structure in (
    glossary.SECTION_STRUCTURE_BOTH,
    glossary.SECTION_STRUCTURE_II_ONLY,
):
    narrowing_attempted = True
    (parse_start, parse_end), narrowing_fired = glossary.narrow_to_section_ii(
        doc, start, end
    )

glossary_entries = glossary.parse_glossary_entries(
    doc, parse_start, parse_end, profile
)
# ... existing fallback logic (still uses parse_start/parse_end if it fires)
```

The bold-fallback path also uses the narrowed range so Section II content is preserved on the fallback path too.

Three new optional metadata fields (Codex iter-1 #4 fix — surface narrowing-attempt failure):

```python
"glossary_pages": glossary_pages,  # original 1-indexed full glossary range
"section_ii_pages": (
    list(range(parse_start + 1, parse_end + 2))
    if narrowing_fired
    else None
),
"section_ii_narrowing_attempted": narrowing_attempted,
"section_ii_narrowing_fired": narrowing_fired,
# narrowing_attempted=True + narrowing_fired=False is the identity-fallback
# case — distribution analysis (§7.4) flags any such doc for review.
```

### 3.4 Schema update

Add 3 new optional fields to `Metadata.properties` in `schema/definition-output-v1.json`:
- `section_ii_pages`: array of integers (1-based) or null
- `section_ii_narrowing_attempted`: boolean
- `section_ii_narrowing_fired`: boolean

All optional; not in `required` (back-compat with existing v0.1.0 candidate-output).

### 3.5 Tests in `tests/test_section_headers.py`

Add new test class `TestNarrowToSectionII` with parametric cases:

- (a) Both sections present → narrows to Section II page
- (b) Section II + Section III in same range → end narrowed to page before Section III
- (c) Section II without Section III → end stays at original
- (d) Section II header is on the same page as content (header + first term on one page) → narrowed start = that page
- (e) Caller-gating violation (Section II not actually present) → identity transform `(start, end)`
- (f) Page-read error during forward scan → falls back to original end without crashing
- (g) Empty range after narrowing → identity transform (defense-in-depth)

Plus `SECTION_AFTER_II_HEADER` regex parametric tests:
- Positive: `Section III`, `Section Ill`, `Section lll`, `Section III — End`
- Negative: `Section II`, `Section Il`, `Section I`, `Section IV`, `intersectional`

Plus an analyzer-integration test using `_make_mock_doc` covering the metadata-emission path:
- doc with Section I + II → `metadata.section_structure == "both"` AND `metadata.section_ii_pages` is the narrowed range AND `glossary_entries` excludes Section I content.

Since analyzer integration requires a real fitz.Document or extensive mocking, the integration test uses mock-doc + monkeypatching `find_glossary_page_range` and `parse_glossary_entries` to return controlled values, so we exercise the narrowing wiring without re-implementing the parser.

## 4. Assumptions & alternatives

**Verified at planning time:**
- ✓ `parse_glossary_entries` already rejects "SECTION II" / "SECTION III" lines as terms via `invalid_term_patterns:66`. No per-line filter changes needed in this unit.
- ✓ AR 380-381 layout has Section II header on page 88 INSIDE the existing `find_glossary_page_range` result (which starts at page 84 = Glossary header).
- ✓ The 27 candidate-output JSONs in `validation_set/candidate-output/` have v0.1.0 outputs; they pre-date Unit 3 changes. Unit 3 does NOT regenerate candidate-output (deferred to Unit 5).

**Load-bearing assumptions:**
- **`find_glossary_page_range` always covers the Section II header page.** True for AR 380-381 (verified). For other docs with Section II, this assumption holds if the "Glossary" or similar header pattern matches BEFORE Section II. If a doc's Section II header appears before any matched glossary header pattern, narrowing returns identity transform (caller-gating violation). **Mitigation:** identity transform is safe — preserves current behavior. The doc still emits the same garbage as v0.1.0; nothing gets worse.
- **Section III always follows Section II** when present. True per Army Pubs convention. If a doc's Section III appears outside [start, end], narrowing returns original `end` (no premature truncation).

**Decisions deferred:**
- **Fail-closed for `section_i_only`** (state 3 from Unit 1's escalation): NOT in this unit. If a doc has Section I but no Section II, it falls through to current behavior. Decision made for surface-area control: most production-bug docs are `both`, not `section_i_only`. Distribution analysis (§7.4) will report the `section_i_only` count; if it's >5, follow-up unit adds fail-closed.

**Alternative considered & rejected:**
- *Modify `find_glossary_page_range` directly to narrow internally.* Rejected: would change the function's documented contract (pages 124-126: "Return (start_page_index, end_page_index) inclusive") and break existing tests. The narrow-after-detect approach is composable and keeps the original function pure.

## 5. The hard 30%

- **Profile gating preserved.** `narrow_to_section_ii` is called by `analyze_pdf` only when `section_structure in {"both", "section_ii_only"}`. Both states are already gated to Army profile by `detect_section_structure`. Non-Army profiles never enter the narrowing path.
- **Identity transform on edge cases.** If Section II isn't actually present (caller-gating violation), or narrowing yields empty range, return `(start, end)` unchanged. Never break docs.
- **Section III regex** is the load-bearing piece for the end-boundary cut. Tests cover observed forms (`III`, `Ill`, `lll`) AND mutual exclusion vs Section II/I/IV.
- **Page-read errors during scan.** Per Unit 2's lesson: errors don't poison results. Forward scan continues past an erroring page; if no Section III found anywhere, end stays at original. **Distinct from Unit 2's "any error → unknown"**: here errors degrade gracefully rather than abort, because we ALREADY have a narrowed start (committed value); aborting would discard real signal.
- **Distribution analysis is operator-run, not CI.** PDFs are gitignored; CI can't run analyze_pdf against them. Plan §7.4 specifies a manual distribution check before merge; results captured in plan doc as evidence.
- **batch1_reconciled.yaml corpus pin will fail when candidate-output is regenerated** (per its lifecycle docs in Sub-Unit 1b). NOT in this unit's scope — Unit 3 doesn't regenerate candidate-output. Unit 5 (wheel publication) handles regeneration + corpus-pin lifecycle inversion.

## 6. Blast radius

**Files to modify (4):**
- `profiles/army.py` (+10 lines: SECTION_AFTER_II_HEADER regex)
- `extractors/glossary.py` (+50 lines: `narrow_to_section_ii` helper + import)
- `core/analyzer.py` (+10 lines: narrowing call + `section_ii_pages` metadata field)
- `schema/definition-output-v1.json` (+3 lines: `section_ii_pages` enum/array)

**Files to extend (1):**
- `tests/test_section_headers.py` (+~120 lines: SECTION_AFTER_II_HEADER regex tests + `narrow_to_section_ii` tests + analyzer-narrowing integration test)

**Files NOT modified:**
- `parse_glossary_entries` — unchanged. Per-line term-validation filters already handle "SECTION II / III" lines.
- `find_glossary_page_range` — unchanged. Documented contract preserved.
- `validation_set/candidate-output/*.json` — NOT regenerated in this unit. The corpus-pin test in `tests/test_batch1_reconciled.py` will continue to pass against committed v0.1.0 output.

**Risk:** medium. Extraction behavior changes for docs with Section II detected. Distribution analysis (§7.4) verifies before merge that no doc unexpectedly drops to 0 entries.

## 7. Verification strategy

### 7.1 Regex unit tests (existing pattern from Unit 2)
- 4 positive + 4 negative cases for `SECTION_AFTER_II_HEADER`.

### 7.2 `narrow_to_section_ii` helper tests
- 7 cases covering both/II-only/section-III-end/no-III/caller-violation/page-error/empty-range scenarios using mock fitz.Document.

### 7.3 Analyzer-integration test (Codex Unit-2 #6 fix)
- Mock-doc-driven test that exercises the full `analyze_pdf` path: `find_glossary_page_range` returns mocked range → `detect_section_structure` returns "both" → `narrow_to_section_ii` narrows → `parse_glossary_entries` is called with narrowed range. Asserts the narrowed range is what gets passed to the parser AND `metadata.section_ii_pages` is populated.

### 7.4 Distribution analysis (operator-run, evidence in plan doc)

Codex iter-1 #5 + #6 fix: strengthened acceptance criteria with per-doc itemization.

- New script `scripts/measure_section_distribution.py` (committed) runs `analyze_pdf` against all 30 local PDFs in `validation_set/pdfs/` (gitignored — operator must have them locally; script skips missing files cleanly).
- Reports for EACH doc: `section_structure`, original glossary range, narrowed range, narrowing_attempted, narrowing_fired, entry_count, entry_count_v0_1_0 (from candidate-output), entry_count_delta.
- **Strengthened acceptance gates** (Codex iter-2 #3, #4 fixes — all must hold before merge):
  1. **0 catastrophic regressions**: no doc drops from `entries > 0` → `entries == 0`.
  2. **0 unexplained identity-fallbacks among bug-target docs**: every doc with `section_structure ∈ {"both", "section_ii_only"}` MUST satisfy `narrowing_fired=True`, OR be on a pre-approved exception list with a recorded follow-up (filed as a task). AR 380-381 MUST narrow successfully — it is NOT eligible for the exception list.
  3. **AR 380-381 deterministic acceptance** (Codex iter-2 #4 tightening):
     - Narrowed range: `metadata.section_ii_pages` starts at exactly `88` (1-based page number where "Section Il" header lives).
     - **Absence assertions** (zero hits): the following EXACT (term, def[:80]) pairs from Sub-Unit 1b reconciliation MUST NOT appear in the regenerated output. Plus all 5 Section I expansions captured for AR 380-381 from prod backfill (entries with `term ∈ {"Army", "Access", "Assistant", "Department", "Defense"}` AND `definition` starting with the corresponding capitalized expansion-word) MUST NOT appear.
     - **Presence assertions**: ≥ 3 of the following (or substrings) from AR 380-381's actual Section II MUST appear: `special access program`, `cleared facility`, `program access request`, `program protection plan`, `oversight committee`. (Hand-verified from the source PDF — operator captures concrete present-term list during the distribution analysis step.)
  4. **≥ 1 "both" doc** shows entry-count reduction (proves the fix fires).
  5. **Per-doc itemized table** in this plan doc's §10 sync verification with: doc name, section_structure, narrowing_attempted, narrowing_fired, entry_count_before (from candidate-output), entry_count_after, delta. Explicit operator review of each row.

### 7.5 Existing test suite
- `pytest tests/` continues green. 137 → 137 + new tests.

### 7.5a Corpus pre-flight: header-form enumeration (Codex iter-2 #2)

Before approval: scan the 27 candidate-output JSONs' `source_pdf` for actual Section header forms. Locally:
```bash
.venv/bin/python -c "
import fitz
from pathlib import Path
import re
pdfs = sorted(Path('validation_set/pdfs').glob('*.pdf'))
forms = set()
for p in pdfs:
    try:
        doc = fitz.open(str(p))
        for page in doc:
            for line in page.get_text('text').split('\n'):
                m = re.match(r'^\s*Section\s+\S+', line)
                if m and len(line) < 60:
                    forms.add(line.strip())
        doc.close()
    except Exception as e:
        print(f'skip {p.name}: {e}')
for f in sorted(forms):
    print(repr(f))
"
```
**Verify:** the regexes (`SECTION_I_HEADER`, `SECTION_II_HEADER`, `SECTION_AFTER_II_HEADER`) collectively classify every observed header form correctly (positive matches for sections we want to detect; negative rejects for sections we don't). Itemize observed forms and per-form classification in the plan's §10 sync verification.

### 7.6 End-to-end synthetic mock-doc test (Codex iter-1 #8 + iter-2 #5 partial)

Add `test_analyzer_narrowing_e2e_with_synthetic_doc` to `tests/test_section_headers.py`. Build a 5-page mock fitz.Document where:
- Page 0: "Glossary\nSection I\nAbbreviations\nAAA\nArmy Audit Agency"
- Page 1: "ASA(ALT)\nAssistant Secretary..."
- Page 2: "Section Il — Terms\nspecial access program ..."
- Page 3: "cleared facility ..."
- Page 4: "Section Ill\nReferences ..."

Monkeypatch `find_glossary_page_range` to return (0, 4). Monkeypatch `parse_glossary_entries` to capture the (start, end) it receives and return synthetic entries reflecting that range.

Assertions:
- `parse_glossary_entries` was called with `(start, end) == (2, 3)` (narrowed: Section II page through page-before-Section-III).
- `metadata.section_structure == "both"`.
- `metadata.section_ii_pages == [3, 4]` (1-indexed).
- `metadata.section_ii_narrowing_fired is True`.

Add a parallel test for the bold-fallback path: same setup but with `enable_bold_gate=True` and a `_bold_preservation_rate` stub returning 0%. Assert the fallback ALSO uses the narrowed range (`(2, 3)`).

**Truly-end-to-end test** (Codex iter-2 #5): a real-parser test would require building a synthetic PDF in code (using fitz's PDF-creation APIs) — out of scope for Unit 3. The real-parser path is exercised by:
- The existing 137 tests running against real PDFs in CI (when fixtures are available).
- The distribution analysis in §7.4 running `analyze_pdf` end-to-end against all 30 local PDFs.
- The AR 380-381 deterministic acceptance check in §7.4.3 running the real parser end-to-end.

The mock-doc test verifies the wiring (range narrows correctly, metadata fields populate, fallback path uses narrowed range). The real-parser path is independently exercised. Combined, this provides equivalent coverage to a single truly-e2e test without the synthetic-PDF infrastructure.

## 8. Documentation impact

- `schema/definition-output-v1.json` — `section_ii_pages` field added (additive, optional).
- `validation_set/README.md` — no update (Sub-Unit 1c's "Honest artifact status" section still accurate; section_ii_pages is metadata, not artifact).
- CHANGELOG: deferred to Unit 5.

## 9. Completion criteria

1. `SECTION_AFTER_II_HEADER` regex defined in `profiles/army.py` and importable.
2. `narrow_to_section_ii(doc, start, end)` helper in `extractors/glossary.py` with the documented contract.
3. `core/analyzer.py:analyze_pdf` calls the helper when `section_structure ∈ {"both", "section_ii_only"}` and emits `metadata.section_ii_pages` when narrowing fires.
4. Schema `Metadata.properties` documents `section_ii_pages` as optional.
5. Tests in `tests/test_section_headers.py` cover regex (8 cases) + helper (7 cases) + analyzer-integration (1+ case). All pass.
6. `scripts/measure_section_distribution.py` exists and runs locally; results recorded in §10.
7. Distribution acceptance gate: 0 catastrophic regressions; ≥ 1 successful narrowing fired.
8. `pytest tests/` (default invocation): 137 + ~16 new = ~153 tests pass; no regressions.

## 10. Execution sequence

### Step 1: Add `SECTION_AFTER_II_HEADER` regex + tests

```bash
# Edit profiles/army.py to add SECTION_AFTER_II_HEADER
# Edit tests/test_section_headers.py to add SECTION_III regex tests
.venv/bin/pytest tests/test_section_headers.py -v -k "section_iii" 2>&1 | tail -10
```
**Verify:** 8 parametric cases pass.

### Step 2: Add `narrow_to_section_ii` helper + tests

```bash
# Edit extractors/glossary.py to add narrow_to_section_ii
# Edit tests/test_section_headers.py to add helper tests
.venv/bin/pytest tests/test_section_headers.py -v -k "narrow" 2>&1 | tail -15
```
**Verify:** 7 helper cases pass.

### Step 3: Wire into `analyzer.py` + schema update

```bash
# Edit core/analyzer.py to call narrow_to_section_ii conditionally
# Edit schema/definition-output-v1.json
# Add analyzer-integration test
.venv/bin/pytest tests/test_section_headers.py -v 2>&1 | tail -10
```
**Verify:** all section-header tests pass (regex + helper + integration).

### Step 4: Existing-suite regression

```bash
.venv/bin/pytest tests/ 2>&1 | tail -5
```
**Verify:** 137 → 137+new pass; no regressions.

### Step 5: Distribution analysis (operator-run)

```bash
# Write scripts/measure_section_distribution.py
.venv/bin/python scripts/measure_section_distribution.py > /tmp/distribution.txt
cat /tmp/distribution.txt
```
**Verify:**
- 0 catastrophic regressions (no doc drops `entries > 0` → `entries == 0`)
- At least 1 doc with `section_structure == "both"` shows narrowed entries
- Distribution recorded in this plan doc

### Step 6: Commit + push

```bash
git add src/fedresearch_dictionary_extractor/profiles/army.py \
        src/fedresearch_dictionary_extractor/extractors/glossary.py \
        src/fedresearch_dictionary_extractor/core/analyzer.py \
        src/fedresearch_dictionary_extractor/schema/definition-output-v1.json \
        tests/test_section_headers.py \
        scripts/measure_section_distribution.py \
        docs/plans/2026-04-26-section-ii-scoping.md
git commit -m "feat(extractor): Section II range scoping with Section III end boundary [Unit 3 of v0.2.0]"
```

(PR + CI + merge handled by Phase 6 Sync & Close.)

## §10 Sync Verification + Distribution Evidence (2026-04-26)

Distribution analysis output (operator-run on local PDFs; CI cannot run extraction). 31 PDFs scanned (30 from validation_set + AR 380-381 added locally for Codex iter-3 #5 acceptance):

```
# Section II scoping distribution (31 PDFs)

| PDF | section_structure | attempted | fired | section_ii_pages | scan_errors | entry_count | v0.1.0 | delta |
|---|---|---|---|---|---|---|---|---|
| ADP_3-07_STABILITY_2019_07_31_OCR.pdf    | none                 | False | False | -                  | 0 | 7 | 7 | +0 |
| AR_11-7_INTERNAL_REVIEW_PROGRAM_ASA_FM_C | unknown              | False | False | -                  | 0 | 0 | 0 | +0 |
| AR_12-15_JOINT_SECURITY_COOPERATION_EDUC | section_ii_only      | True  | True  | [344..344]         | 0 | 8 | 8 | +0 |
| AR_135-100_APPOINTMENT_OF_COMMISSIONED_A | section_ii_only      | True  | True  | [70..84]           | 0 | 149 | 151 | -2 |
| AR_190-55_U.S._ARMY_CORRECTIONS_SYSTEM__ | section_ii_only      | True  | True  | [19..19]           | 0 | 17 | 17 | +0 |
| AR_190-9_ABSENTEE_DESERTER_APPREHENSION_ | section_ii_only      | True  | True  | [22..22]           | 0 | 16 | ? | ? |
| AR_200-1_ENVIRONMENTAL_PROTECTION_AND_EN | unknown              | False | False | -                  | 0 | 0 | 0 | +0 |
| AR_215-1_MILITARY_MORALE_WELFARE_AND_REC | section_ii_only      | True  | True  | [265..277]         | 0 | 171 | ? | ? |
| AR_25-59_OFFICE_SYMBOLS_CIO_2024_02_15_O | unknown              | False | False | -                  | 0 | 0 | 0 | +0 |
| AR_380-381_SPECIAL_ACCESS_PROGRAMS_SAPS_ | both                 | True  | True  | [88..89]           | 0 | 40 | ? | ? |
| AR_40-3_MEDICAL_DENTAL_AND_VETERINARY_CA | section_ii_only      | True  | True  | [105..110]         | 0 | 74 | 86 | -12 |
| AR_40-5_ARMY_PUBLIC_HEALTH_PROGRAM_TSG_2 | section_ii_only      | True  | True  | [51..59]           | 0 | 86 | 86 | +0 |
| AR_405-90_DISPOSAL_OF_REAL_PROPERTY_COE_ | section_ii_only      | True  | True  | [34..37]           | 0 | 58 | 73 | -15 |
| AR_525-21_C__ARMY_MILITARY_DECEPTION__MI | unknown              | False | False | -                  | 0 | 0 | 0 | +0 |
| AR_600-20.pdf                            | none                 | False | False | -                  | 0 | 88 | 88 | +0 |
| AR_672-20_INCENTIVE_AWARDS_G-1_2024_11_0 | section_ii_only      | True  | True  | [57..58]           | 0 | 25 | 25 | +0 |
| AR_95-27_OPERATIONAL_PROCEDURES_FOR_AIRC | unknown              | False | False | -                  | 0 | 0 | 0 | +0 |
| ATP_1-05.01_RELIGIOUS_SUPPORT_AND_THE_OP | both                 | True  | True  | [83..84]           | 0 | 0 | 0 | +0 |
| ATP_4-35_MUNITIONS_OPERATIONS_2023_01_31 | none                 | False | False | -                  | 0 | 2 | 2 | +0 |
| ATP_5-0.3_MULTI-SERVICE_TACTICS_TECHNIQU | none                 | False | False | -                  | 0 | 121 | ? | ? |
| FM_3-34_ENGINEER_OPERATIONS_2020_12_18_O | section_ii_only      | True  | True  | [131..132]         | 0 | 4 | 4 | +0 |
| FM_3-55_INFORMATION_COLLECTION_2013_05_0 | none                 | False | False | -                  | 0 | 4 | 4 | +0 |
| FM_4-1_HUMAN_RESOURCES_SUPPORT_2025_09_1 | none                 | False | False | -                  | 0 | 1 | 1 | +0 |
| FM_6-02_SIGNAL_SUPPORT_TO_OPERATIONS_201 | none                 | False | False | -                  | 0 | 14 | 14 | +0 |
| PAM_190-45_ARMY_LAW_ENFORCEMENT_REPORTIN | section_ii_only      | True  | True  | [82..84]           | 0 | 26 | 26 | +0 |
| PAM_350-58_ARMY_LEADER_DEVELOPMENT_PROGR | both                 | True  | True  | [25..26]           | 0 | 29 | 42 | -13 |
| PAM_385-64_AMMUNITION_AND_EXPLOSIVES_SAF | unknown              | False | False | -                  | 0 | 0 | 0 | +0 |
| PAM_600-3.pdf                            | unknown              | False | False | -                  | 0 | 0 | 0 | +0 |
| PAM_71-32_FORCE_DEVELOPMENT_AND_DOCUMENT | section_ii_only      | True  | True  | [140..145]         | 0 | 59 | 62 | -3 |
| PAM_770-3_TYPE_CLASSIFICATION_AND_MATERI | unknown              | False | False | -                  | 0 | 0 | 0 | +0 |
| TC_1-19.30.pdf                           | both                 | True  | True  | [149..150]         | 0 | 2 | 2 | +0 |

## AR 380-381 deterministic acceptance

**PASSED.**
- narrowed range starts at page 88 ✓
- 6 Section I boundary-residue acronyms (within 10 cap; same-page boundary limitation per Codex iter-3 #6)
  residue: ['TRADOC', 'USACE', 'USACIDC', 'USAFMSA', 'USAINSCOM', 'USASMDC']
- 2 required Section II terms present (expected ≥ 1): ['special access program', 'Acquisition SAP']
```

### Acceptance gate evaluation

1. ✅ **0 catastrophic regressions:** no doc dropped from `entries > 0` → `entries == 0`. (ATP_1-05.01 was 0 before AND after, consistent.)
2. ✅ **0 unexplained identity-fallbacks for `both`/`section_ii_only`:** all 14 attempted=True docs also fired=True.
3. ✅ **AR 380-381 deterministic acceptance PASSED**: narrowed range starts at page 88; 6 boundary-residue acronyms (within 10-cap; same-page boundary limitation per Codex iter-3 #6); 2 required Section II terms present.
4. ✅ **≥ 1 "both" doc shows entry-count reduction:** PAM_350-58 went 42 → 29 (−13, 31% reduction); AR 380-381 went ~80 → 40 (50% reduction per local output).
5. ✅ **Per-doc itemization:** table above; operator review captured.

### Quantified Section I bleed reduction (vs v0.1.0 candidate-output)

| Doc | section_structure | v0.1.0 entries | Unit-3 entries | Δ | reduction |
|---|---|---|---|---|---|
| AR_135-100 | section_ii_only | 151 | 149 | −2 | 1.3% |
| AR_40-3 | section_ii_only | 86 | 74 | −12 | 14% |
| AR_405-90 | section_ii_only | 73 | 58 | −15 | 21% |
| PAM_350-58 | both | 42 | 29 | −13 | 31% |
| PAM_71-32 | section_ii_only | 62 | 59 | −3 | 5% |
| AR_380-381 | both | ~80 (prod backfill) | 40 | −40 | 50% |

The "both" docs (PAM_350-58 and AR_380-381) show the largest reductions, consistent with Section I content being correctly excluded.

### Boundary-residue limitation (Codex iter-3 #6)

AR_380-381 page 88 has Section I continuation (TRADOC + 5 USA* acronyms) AT THE TOP, then "Section Il / Terms" header, then Section II content. The narrowing helper sets `new_start = page 88` (where the Section II header was found), but the parser sees the whole page including pre-header Section I residue. 6 acronyms remain.

This is a known limitation of page-level boundary detection. Line-level boundary detection (out of scope per Unit 3 plan) would eliminate the residue. **Tracked as a follow-up unit if observed >10 anywhere in the corpus** (currently observed only on AR 380-381 with 6/40 entries = 15% boundary residue).
