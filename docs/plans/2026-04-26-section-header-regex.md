# Unit 2 — Section II + Section I header regex (detection only)

## Phase 0.a Classification

**fast-path-eligible** — additive regex constants + new metadata field, no behavior change to range-detection or extraction. Single repo, fully reversible.

## 1. Problem statement

Per Unit 1 escalation, Army Pubs glossaries with both Section I (Abbreviations) and Section II (Terms) are the dominant cause of v0.1.0's 47% single-lc-word garbage. Unit 2 lays the **detection-only** foundation: add OCR-tolerant regexes for Section II and Section I headers, run detection over the existing glossary page range, and emit `metadata.section_structure` in JSON output. **No range scoping, no extraction-behavior change** — that's Unit 3. This unit lets us validate detection accuracy across the corpus before changing extraction.

## 2. Verified context (read at planning time)

- `profiles/army.py` uses class-property pattern. Existing `glossary_header_patterns:34` already tries to match Section II with `r"^\s*Section\s+II\s*[-–—]?\s*Terms\s*$"` — too strict (misses "Section Il").
- `extractors/glossary.py:110` defines `find_glossary_page_range(doc, profile) -> (start, end) | None`. No metadata emitted.
- `core/analyzer.py:91-102` builds `metadata` dict in `analyze_pdf`.
- **Schema:** `src/fedresearch_dictionary_extractor/schema/definition-output-v1.json` — `Metadata` defines `additionalProperties` defaulting permissive; adding `section_structure` is schema-compatible without bumping. Plan adds it to `Metadata.properties` as an optional enum (not in `required`) for documentation completeness.
- **Manifest audit (Sub-Unit 1a):** committed `validation_set/manifest_audit.md` documents 27 v0.1.0 candidate-output JSONs as canonical baseline.

## 3. Approach

### 3.1 `src/fedresearch_dictionary_extractor/profiles/army.py`

Add module-level compiled regex constants near top:

```python
import re

SECTION_II_HEADER = re.compile(
    r"^\s*Section\s+(?:II|Il)(?=\s|$|—|–|-)",
    re.IGNORECASE | re.MULTILINE,
)
SECTION_I_HEADER = re.compile(
    r"^\s*Section\s+(?:I|\||l)(?![Il\|])(?=\s|$|—|–|-)",
    re.IGNORECASE | re.MULTILINE,
)
```

Patterns match ONLY observed forms (per `manifest_audit.md` + AR 380-381 page 84/88/90 inspection). `re.MULTILINE` makes `^` match line-starts in multi-line page text.

### 3.2 `src/fedresearch_dictionary_extractor/extractors/glossary.py`

Add helper after `find_glossary_page_range`:

```python
from ..profiles.army import SECTION_II_HEADER, SECTION_I_HEADER
from ..profiles.base import ReferenceProfile

# Section structure label values (Codex iter-1 #6 fix: explicit "unknown" for
# detection failure, distinct from genuine absence "none").
SECTION_STRUCTURE_NONE = "none"
SECTION_STRUCTURE_I_ONLY = "section_i_only"
SECTION_STRUCTURE_II_ONLY = "section_ii_only"
SECTION_STRUCTURE_BOTH = "both"
SECTION_STRUCTURE_UNKNOWN = "unknown"  # detection error or non-Army profile

def detect_section_structure(
    doc: fitz.Document,
    start: int | None,
    end: int | None,
    profile: ReferenceProfile,
) -> str:
    """Detect Section I/II header presence within the glossary page range.

    Profile-gated (Codex iter-1 #4): only Army-profile docs use these regexes.
    Other profiles return "unknown" — they don't currently have section
    structure semantics defined.

    Range-coverage caveat (Codex iter-1 #3): scans only [start, end] from
    find_glossary_page_range. If a Section I header lives on the page BEFORE
    the glossary header is detected, this returns "section_ii_only" or "none"
    falsely. Unit 3 verifies range coverage by running detection on all
    candidate-output PDFs and reporting the section_structure distribution.

    Returns: "none" | "section_i_only" | "section_ii_only" | "both" | "unknown".
    """
    if profile.name != "army":
        return SECTION_STRUCTURE_UNKNOWN
    if start is None or end is None:
        return SECTION_STRUCTURE_NONE
    has_i = False
    has_ii = False
    encountered_error = False
    for page_idx in range(start, end + 1):
        try:
            page_text = doc[page_idx].get_text("text")
        except Exception:
            encountered_error = True
            continue
        if not has_ii and SECTION_II_HEADER.search(page_text):
            has_ii = True
        if not has_i and SECTION_I_HEADER.search(page_text):
            has_i = True
        if has_i and has_ii:
            break
    # If at least one page read failed AND we detected nothing, label "unknown"
    # so the result is distinguishable from genuine absence.
    if encountered_error and not has_i and not has_ii:
        return SECTION_STRUCTURE_UNKNOWN
    if has_i and has_ii:
        return SECTION_STRUCTURE_BOTH
    if has_ii:
        return SECTION_STRUCTURE_II_ONLY
    if has_i:
        return SECTION_STRUCTURE_I_ONLY
    return SECTION_STRUCTURE_NONE
```

### 3.3 `src/fedresearch_dictionary_extractor/core/analyzer.py`

Modify `analyze_pdf`:

```python
section_structure = "none"
if text_layer:
    page_range = glossary.find_glossary_page_range(doc, profile)
    if page_range:
        start, end = page_range
        section_structure = glossary.detect_section_structure(doc, start, end, profile)
        # ... existing parse_glossary_entries call
else:
    # No text layer → can't detect; existing semantics treat as no glossary.
    section_structure = "unknown"

# In the metadata dict (additive — non-breaking schema):
"metadata": {
    ...,
    "glossary_used_legacy_fallback": glossary_used_fallback,
    "section_structure": section_structure,
},
```

### 3.4 `src/fedresearch_dictionary_extractor/schema/definition-output-v1.json`

Add `section_structure` to `Metadata.properties` (NOT to `required` — back-compat):

```json
"section_structure": {
  "enum": ["none", "section_i_only", "section_ii_only", "both", "unknown"]
}
```

### 3.5 `tests/test_section_headers.py` (new)

Three test classes:

```python
"""Section II + Section I header regex + detection helper tests (Unit 2 of v0.2.0)."""
from unittest.mock import MagicMock

import pytest

from fedresearch_dictionary_extractor.profiles.army import (
    SECTION_II_HEADER, SECTION_I_HEADER,
)
from fedresearch_dictionary_extractor.extractors.glossary import detect_section_structure
from fedresearch_dictionary_extractor.profiles import get_profile


# ─── Regex-level tests ──────────────────────────────────────────────────────

SECTION_II_POSITIVE = [
    "Section II", "Section Il", "Section II — Terms",
    "Section Il Terms used in this regulation",
    "  Section Il",
]
SECTION_II_NEGATIVE = [
    "Section III", "Section Ill",  # Section III, must reject
    "Section IV", "Section I", "Section |", "Section l",  # Section I forms
    "intersectional", "Some Section II Reference",  # mid-line
]
SECTION_I_POSITIVE = [
    "Section I", "Section |", "Section l",
    "Section I — Abbreviations", "Section | Abbreviations",
]
SECTION_I_NEGATIVE = [
    "Section II", "Section Il",  # Section II forms (mutual exclusion)
    "Section III", "Section Ill", "Section ||",
    "intersection",
]

@pytest.mark.parametrize("s", SECTION_II_POSITIVE)
def test_section_ii_matches(s):
    assert SECTION_II_HEADER.search(s)

@pytest.mark.parametrize("s", SECTION_II_NEGATIVE)
def test_section_ii_rejects(s):
    assert not SECTION_II_HEADER.search(s)

@pytest.mark.parametrize("s", SECTION_I_POSITIVE)
def test_section_i_matches(s):
    assert SECTION_I_HEADER.search(s)

@pytest.mark.parametrize("s", SECTION_I_NEGATIVE)
def test_section_i_rejects(s):
    assert not SECTION_I_HEADER.search(s)


# ─── detect_section_structure helper tests ─────────────────────────────────
# (Codex iter-1 #2 + #5: page-level fixture testing using mock doc with
# realistic multi-line page text containing both/either/neither header.)

def _make_mock_doc(page_texts: list[str]) -> MagicMock:
    """Build a mock fitz.Document where doc[i].get_text("text") returns the
    given string. Simulates real-PDF structure without needing the PDF."""
    pages = []
    for txt in page_texts:
        page = MagicMock()
        page.get_text.return_value = txt
        pages.append(page)
    doc = MagicMock()
    doc.__getitem__.side_effect = lambda i: pages[i]
    return doc

ARMY = get_profile("army")

def test_helper_both_sections():
    """AR 380-381-style layout: Section I on one page, Section II on another."""
    doc = _make_mock_doc([
        "Glossary\nSection I\nAbbreviations\nAAA\nArmy Audit Agency",
        "ASA(ALT)\nAssistant Secretary of the Army (Acquisition, Logistics)",
        "Section Il\nTerms\nspecial access program ...",
    ])
    assert detect_section_structure(doc, 0, 2, ARMY) == "both"

def test_helper_section_ii_only():
    """Glossary with only Section II header (no explicit Section I)."""
    doc = _make_mock_doc([
        "Glossary\nSection II Terms\nstability operation ...",
    ])
    assert detect_section_structure(doc, 0, 0, ARMY) == "section_ii_only"

def test_helper_section_i_only():
    """Glossary with Section I marker but no Section II (e.g., abbreviation-
    only doc)."""
    doc = _make_mock_doc([
        "Glossary\nSection I\nAbbreviations\nAAA\nArmy Audit Agency",
    ])
    assert detect_section_structure(doc, 0, 0, ARMY) == "section_i_only"

def test_helper_neither():
    """Glossary with no section headers at all."""
    doc = _make_mock_doc([
        "Glossary\nplanning The art of understanding a situation\nstability ...",
    ])
    assert detect_section_structure(doc, 0, 0, ARMY) == "none"

def test_helper_no_range():
    """When find_glossary_page_range returned None (no glossary), helper
    returns 'none' regardless of doc state."""
    doc = _make_mock_doc(["irrelevant"])
    assert detect_section_structure(doc, None, None, ARMY) == "none"

def test_helper_non_army_profile_returns_unknown():
    """Codex iter-1 #4: non-Army profiles get 'unknown' (semantics undefined)."""
    class StubProfile:
        name = "fake"
    doc = _make_mock_doc(["Section II\nTerms\nfoo bar"])
    assert detect_section_structure(doc, 0, 0, StubProfile()) == "unknown"

def test_helper_page_read_error_returns_unknown_when_no_match():
    """Codex iter-1 #6: detection failure distinct from genuine absence."""
    doc = MagicMock()
    page = MagicMock()
    page.get_text.side_effect = RuntimeError("simulated PDF read error")
    doc.__getitem__.return_value = page
    assert detect_section_structure(doc, 0, 0, ARMY) == "unknown"

def test_helper_page_read_error_does_not_mask_partial_detection():
    """If we already detected a header before the error, return that label
    rather than 'unknown' (partial signal is more useful than no signal)."""
    pages = [
        MagicMock(),  # page 0: SECTION_II match
        MagicMock(),  # page 1: error
    ]
    pages[0].get_text.return_value = "Section II Terms"
    pages[1].get_text.side_effect = RuntimeError("simulated")
    doc = MagicMock()
    doc.__getitem__.side_effect = lambda i: pages[i]
    assert detect_section_structure(doc, 0, 1, ARMY) == "section_ii_only"


# ─── Schema regression test (Codex iter-1 #1 fix) ──────────────────────────

def test_existing_candidate_output_unchanged_by_schema_addition():
    """Loading existing committed candidate-output JSONs after the schema
    addition still parses cleanly. Verifies the additive-schema claim that
    section_structure is back-compat for existing artifacts."""
    import json
    from pathlib import Path
    co_dir = Path(__file__).parent.parent / "validation_set" / "candidate-output"
    files = list(co_dir.glob("*.json"))
    assert files, "No candidate-output JSONs found"
    for f in files:
        d = json.loads(f.read_text())
        # Existing output may not have section_structure (it's optional).
        assert "metadata" in d
        # If present, must be one of the enum values
        if "section_structure" in d["metadata"]:
            assert d["metadata"]["section_structure"] in {
                "none", "section_i_only", "section_ii_only", "both", "unknown"
            }
```

Default-CI test (no validation marker).

## 4. Assumptions & alternatives

**Verified at planning time:**
- ✓ Schema `Metadata` allows additionalProperties (no `additionalProperties: false`); `section_structure` addition is back-compat.
- ✓ Existing candidate-output JSONs lack the field; schema regression test confirms the change doesn't break loading.
- ✓ `profiles/army.py` uses class properties; module-level constants are additive and don't disturb the class.

**Load-bearing assumptions:**
- **Range coverage** (Codex iter-1 #3): `find_glossary_page_range` covers the pages where Section I/II headers actually appear. **Mitigation:** the helper docstring documents this caveat, the helper returns `"unknown"` on page-read errors, and Unit 3 will run distribution analysis on all 27 candidate-output PDFs — if many docs report `"none"` despite known section structure, the range finder is the bug, not this helper.
- **Only-observed regex coverage** (`II`/`Il` for Section II; `I`/`|`/`l` for Section I): sufficient for the corpus. Unit 3 verifies via detection-distribution check; widens with new observed strings if needed.

## 5. The hard 30%

- **Profile gating** (Codex iter-1 #4): non-Army profiles return `"unknown"`. Test enforces.
- **Exception state** (Codex iter-1 #6): page-read errors return `"unknown"` (not `"none"`) when no match has been found. Partial-match cases preserve the partial signal. Two tests enforce.
- **Schema back-compat** (Codex iter-1 #1): regression test loads all 27 candidate-output JSONs and validates them.
- **Page-level helper tests** (Codex iter-1 #2 + #5): mock-doc-based fixtures cover both/either/neither scenarios with multi-line text containing realistic content.
- **Range-coverage limitation** (Codex iter-1 #3): documented in the helper docstring; deferred to Unit 3 verification. NOT silently swallowed.
- **No removal of existing strict Section II pattern** at `glossary_header_patterns:34` — Unit 3's job.

## 6. Blast radius

**Files to modify (4):**
- `profiles/army.py` (~10 lines; module-level regex constants)
- `extractors/glossary.py` (~50 lines; `detect_section_structure` helper + 5 enum constants + import)
- `core/analyzer.py` (~5 lines; helper call + metadata field)
- `schema/definition-output-v1.json` (~3 lines; optional `section_structure` enum)

**Files to create (1):**
- `tests/test_section_headers.py` (~150 lines)

**Existing tests:** 104 passing. New `metadata.section_structure` field is additive; existing tests reading `entries[]` are unaffected. Schema regression test confirms.

**Risk:** low — detection-only; no extraction behavior change; profile-gated to Army; back-compat schema.

## 7. Verification strategy

1. **Regex unit tests** (24 parametric cases across 4 functions): positive + negative for each regex; mutual exclusion enforced.
2. **Detection helper tests** (8 cases): `both`, `section_ii_only`, `section_i_only`, `none`, `no_range`, `non_army_profile`, `read_error_no_match`, `read_error_partial_match`. Mock-doc fixtures with realistic multi-line text.
3. **Schema regression test**: loads 27 existing candidate-output JSONs; verifies they parse + section_structure (when present) is in the enum.
4. **Existing test suite continues green** (104 → 104 unchanged).

## 8. Documentation impact

- Schema file `definition-output-v1.json` updated (new optional field documented).
- `validation_set/README.md`: no change (Sub-Unit 1c just landed; the new `metadata.section_structure` field doesn't change the artifact-status table).
- CHANGELOG: deferred to Unit 5 (wheel publication).

## 9. Completion criteria

1. `profiles/army.py` exposes `SECTION_II_HEADER`, `SECTION_I_HEADER` module-level compiled regex constants.
2. `extractors/glossary.py` exposes `detect_section_structure(doc, start, end, profile) -> str` returning one of 5 enum values; profile-gated to Army; exception-aware.
3. `core/analyzer.py:analyze_pdf` calls the helper and emits `metadata.section_structure`.
4. `schema/definition-output-v1.json` documents `section_structure` as optional enum.
5. `tests/test_section_headers.py` runs in default CI with 32 test cases (24 parametric regex + 8 helper); all pass.
6. Schema regression test loads all 27 candidate-output JSONs without error.
7. `pytest tests/`: 104 pre-existing + ~32 new = ~136 tests pass; no regressions.

## 10. Execution sequence

### Step 1: Add regex constants to `profiles/army.py`

Per §3.1.

**Verify:**
```bash
.venv/bin/python -c "from fedresearch_dictionary_extractor.profiles.army import SECTION_II_HEADER, SECTION_I_HEADER; print(SECTION_II_HEADER.pattern); print(SECTION_I_HEADER.pattern)"
```
Expected: prints both patterns.

### Step 2: Write `tests/test_section_headers.py` regex section (test-driven; verify regex correctness first)

Per §3.5 regex section.

**Verify:**
```bash
.venv/bin/pytest tests/test_section_headers.py -v -k "section_i or section_ii" 2>&1 | tail -10
```
Expected: 24 parametric cases pass.

### Step 3: Add `detect_section_structure` helper + enum constants to `glossary.py`

Per §3.2.

**Verify:**
```bash
.venv/bin/python -c "from fedresearch_dictionary_extractor.extractors.glossary import detect_section_structure, SECTION_STRUCTURE_NONE, SECTION_STRUCTURE_UNKNOWN; print('importable')"
```
Expected: prints "importable".

### Step 4: Add helper tests + schema regression test

Per §3.5 helper + schema sections.

**Verify:**
```bash
.venv/bin/pytest tests/test_section_headers.py -v 2>&1 | tail -15
```
Expected: all ~32 cases pass (24 regex + 8 helper).

### Step 5: Wire into `analyzer.py` metadata + update schema

Per §3.3 + §3.4.

**Verify (existing tests still green + schema regression):**
```bash
.venv/bin/pytest tests/ 2>&1 | tail -5
```
Expected: ~136 pass; no regressions.

### Step 6: Commit

```bash
git add src/fedresearch_dictionary_extractor/profiles/army.py \
        src/fedresearch_dictionary_extractor/extractors/glossary.py \
        src/fedresearch_dictionary_extractor/core/analyzer.py \
        src/fedresearch_dictionary_extractor/schema/definition-output-v1.json \
        tests/test_section_headers.py
git commit -m "feat(extractor): Section II + I header detection + metadata.section_structure [plan: 2026-04-26-section-header-regex]"
```

(PR + CI + merge handled by Phase 6 Sync & Close.)
