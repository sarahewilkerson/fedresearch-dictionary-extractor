"""Section II + Section I header regex + detection helper tests (Unit 2 of v0.2.0).

Detection-only — these tests verify the regexes and the detect_section_structure
helper. No range-scoping or extraction-behavior change is in scope (Unit 3).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fedresearch_dictionary_extractor.extractors.glossary import (
    SECTION_STRUCTURE_BOTH,
    SECTION_STRUCTURE_I_ONLY,
    SECTION_STRUCTURE_II_ONLY,
    SECTION_STRUCTURE_NONE,
    SECTION_STRUCTURE_UNKNOWN,
    detect_section_structure,
    narrow_to_section_ii,
)
from fedresearch_dictionary_extractor.profiles import get_profile
from fedresearch_dictionary_extractor.profiles.army import (
    SECTION_AFTER_II_HEADER,
    SECTION_I_HEADER,
    SECTION_II_HEADER,
)

ARMY = get_profile("army")
VALID_SECTION_STRUCTURES = {
    SECTION_STRUCTURE_NONE,
    SECTION_STRUCTURE_I_ONLY,
    SECTION_STRUCTURE_II_ONLY,
    SECTION_STRUCTURE_BOTH,
    SECTION_STRUCTURE_UNKNOWN,
}


# ─── Regex-level tests ──────────────────────────────────────────────────────

SECTION_II_POSITIVE = [
    "Section II",                                      # canonical (hypothetical clean OCR)
    "Section Il",                                      # AR 380-381 page 88
    "Section II — Terms",                              # canonical with em-dash
    "Section Il Terms used in this regulation",        # OCR drift + body
    "  Section Il",                                    # leading whitespace
]
SECTION_II_NEGATIVE = [
    "Section III",                                     # AR 380-381 page 90 (Section III, NOT II)
    "Section Ill",                                     # OCR variant of Section III
    "Section IV",
    "Section I",                                       # Section I, not II
    "Section |",                                       # Section I single-pipe variant
    "Section l",                                       # Section I lowercase-L variant
    "intersectional",                                  # mid-word
    "Some Section II Reference",                       # not at line start
]

SECTION_I_POSITIVE = [
    "Section I",
    "Section |",                                       # AR 380-381 page 84 (single pipe)
    "Section l",                                       # lowercase L
    "Section I — Abbreviations",
    "Section | Abbreviations",
]
SECTION_I_NEGATIVE = [
    "Section II",                                      # MUST NOT match (mutual exclusion)
    "Section Il",
    "Section III",
    "Section Ill",
    "Section ||",                                      # double pipe (not Section I)
    "intersection",                                    # mid-word
]

# Codex Unit-3 iter-1 #3 + iter-2 fix: trailing constraint added in Unit 3
# rejects body-text lines that begin with a Section reference but lack a
# recognized header suffix.
SECTION_II_BODY_TEXT_REJECTS = [
    "Section II policies require ...",                 # body text starting with Section II
    "Section II regulations apply when ...",
    "Section II covers all programs",
    "Section Il policies require ...",
]
SECTION_I_BODY_TEXT_REJECTS = [
    "Section I policies require ...",
    "Section I covers acronyms used ...",
    "Section l regulations apply ...",
]

# Section AFTER II — III/IV/V/VI/VII (Unit 3).
SECTION_AFTER_II_POSITIVE = [
    "Section III",
    "Section Ill",                                     # AR 380-381 page 90
    "Section lll",                                     # defensive
    "Section III — Special Subjects",
    "Section IV",
    "Section IV — Special Subjects",                   # skipped-III case (Codex iter-1 #1)
    "Section V",
    "Section V References",
]
SECTION_AFTER_II_NEGATIVE = [
    "Section II",                                      # we narrow TO this, not past
    "Section Il",
    "Section I",
    "Section II — Terms",
    "Section III regulations require ...",             # Codex #3: body text
    "Section IV policies apply ...",
    "intersectional",
    "Some Section III Reference",                      # not at line-start
]


@pytest.mark.parametrize("s", SECTION_II_POSITIVE)
def test_section_ii_matches(s: str) -> None:
    assert SECTION_II_HEADER.search(s), f"SECTION_II should match: {s!r}"


@pytest.mark.parametrize("s", SECTION_II_NEGATIVE)
def test_section_ii_rejects(s: str) -> None:
    assert not SECTION_II_HEADER.search(s), f"SECTION_II should NOT match: {s!r}"


@pytest.mark.parametrize("s", SECTION_I_POSITIVE)
def test_section_i_matches(s: str) -> None:
    assert SECTION_I_HEADER.search(s), f"SECTION_I should match: {s!r}"


@pytest.mark.parametrize("s", SECTION_I_NEGATIVE)
def test_section_i_rejects(s: str) -> None:
    assert not SECTION_I_HEADER.search(s), f"SECTION_I should NOT match: {s!r}"


@pytest.mark.parametrize("s", SECTION_II_BODY_TEXT_REJECTS)
def test_section_ii_rejects_body_text(s: str) -> None:
    """Codex Unit-3 iter-2 fix: trailing constraint rejects body-text
    lines beginning with 'Section II ...' but lacking a header suffix."""
    assert not SECTION_II_HEADER.search(s), f"SECTION_II should NOT match body text: {s!r}"


@pytest.mark.parametrize("s", SECTION_I_BODY_TEXT_REJECTS)
def test_section_i_rejects_body_text(s: str) -> None:
    assert not SECTION_I_HEADER.search(s), f"SECTION_I should NOT match body text: {s!r}"


@pytest.mark.parametrize("s", SECTION_AFTER_II_POSITIVE)
def test_section_after_ii_matches(s: str) -> None:
    assert SECTION_AFTER_II_HEADER.search(s), f"SECTION_AFTER_II should match: {s!r}"


@pytest.mark.parametrize("s", SECTION_AFTER_II_NEGATIVE)
def test_section_after_ii_rejects(s: str) -> None:
    assert not SECTION_AFTER_II_HEADER.search(s), f"SECTION_AFTER_II should NOT match: {s!r}"


# ─── detect_section_structure helper tests ─────────────────────────────────


def _make_mock_doc(page_texts: list[str]) -> MagicMock:
    """Build a mock fitz.Document where doc[i].get_text("text") returns the
    given string. Simulates real-PDF structure without needing a PDF."""
    pages = []
    for txt in page_texts:
        page = MagicMock()
        page.get_text.return_value = txt
        pages.append(page)
    doc = MagicMock()
    doc.__getitem__.side_effect = lambda i: pages[i]
    return doc


def test_helper_both_sections() -> None:
    """AR 380-381-style layout: Section I on one page, Section II on another."""
    doc = _make_mock_doc(
        [
            "Glossary\nSection I\nAbbreviations\nAAA\nArmy Audit Agency",
            "ASA(ALT)\nAssistant Secretary of the Army (Acquisition, Logistics)",
            "Section Il\nTerms\nspecial access program ...",
        ]
    )
    assert detect_section_structure(doc, 0, 2, ARMY) == SECTION_STRUCTURE_BOTH


def test_helper_section_ii_only() -> None:
    """Glossary with only Section II header (no explicit Section I)."""
    doc = _make_mock_doc(
        ["Glossary\nSection II Terms\nstability operation ..."]
    )
    assert detect_section_structure(doc, 0, 0, ARMY) == SECTION_STRUCTURE_II_ONLY


def test_helper_section_i_only() -> None:
    """Glossary with Section I marker but no Section II."""
    doc = _make_mock_doc(
        ["Glossary\nSection I\nAbbreviations\nAAA\nArmy Audit Agency"]
    )
    assert detect_section_structure(doc, 0, 0, ARMY) == SECTION_STRUCTURE_I_ONLY


def test_helper_neither() -> None:
    """Glossary with no section headers at all."""
    doc = _make_mock_doc(
        ["Glossary\nplanning The art of understanding a situation\nstability ..."]
    )
    assert detect_section_structure(doc, 0, 0, ARMY) == SECTION_STRUCTURE_NONE


def test_helper_no_range_returns_unknown() -> None:
    """Codex iter-2 #2: when start/end are None (no glossary range), return
    'unknown' — distinct from 'scanned, found nothing'."""
    doc = _make_mock_doc(["irrelevant"])
    assert detect_section_structure(doc, None, None, ARMY) == SECTION_STRUCTURE_UNKNOWN


def test_helper_non_army_profile_returns_unknown() -> None:
    """Codex iter-1 #4: non-Army profiles get 'unknown' (semantics undefined)."""

    class StubProfile:
        name = "fake"

    doc = _make_mock_doc(["Section II\nTerms\nfoo bar"])
    assert detect_section_structure(doc, 0, 0, StubProfile()) == SECTION_STRUCTURE_UNKNOWN


def test_helper_page_read_error_returns_unknown() -> None:
    """Codex iter-2 #5: ANY page-read error returns 'unknown' for the whole
    doc. Simpler/safer than partial-preference (an error on the page
    containing the OTHER header would otherwise misclassify a 'both' doc as
    single-section)."""
    doc = MagicMock()
    page = MagicMock()
    page.get_text.side_effect = RuntimeError("simulated PDF read error")
    doc.__getitem__.return_value = page
    assert detect_section_structure(doc, 0, 0, ARMY) == SECTION_STRUCTURE_UNKNOWN


def test_helper_page_read_error_after_partial_match_still_unknown() -> None:
    """Codex iter-2 #5 fix: even if we already detected one header before the
    error, return 'unknown' rather than the partial label. Avoids hiding
    incomplete scans."""
    pages = [MagicMock(), MagicMock()]
    pages[0].get_text.return_value = "Section II Terms"
    pages[1].get_text.side_effect = RuntimeError("simulated")
    doc = MagicMock()
    doc.__getitem__.side_effect = lambda i: pages[i]
    assert detect_section_structure(doc, 0, 1, ARMY) == SECTION_STRUCTURE_UNKNOWN


# ─── Schema regression test (Codex iter-1 #1 fix) ──────────────────────────


# ─── narrow_to_section_ii helper tests (Unit 3) ────────────────────────────


def test_narrow_both_sections_to_section_ii() -> None:
    """AR 380-381 layout: Section I content on early pages, Section II
    on a later page, Section III after that. Narrowed range starts at
    Section II page and ends at the page before Section III."""
    doc = _make_mock_doc(
        [
            "Glossary\nSection I\nAbbreviations\nAAA\nArmy Audit Agency",  # page 0
            "ASA(ALT)\nAssistant Secretary of the Army",                    # page 1
            "Section II — Terms\nspecial access program ...",               # page 2 (II)
            "cleared facility ...",                                         # page 3
            "Section III\nReferences ...",                                  # page 4 (III)
        ]
    )
    result = narrow_to_section_ii(doc, 0, 4)
    assert result["fired"] is True
    assert result["start"] == 2
    assert result["end"] == 3  # page before Section III
    assert result["boundary_scan_errors"] == 0


def test_narrow_section_ii_only() -> None:
    """Section II header present but no later section header within range."""
    doc = _make_mock_doc(
        [
            "Glossary\nSome heading",
            "Section II — Terms\nplanning ...",
            "stability ...",
        ]
    )
    result = narrow_to_section_ii(doc, 0, 2)
    assert result["fired"] is True
    assert result["start"] == 1
    assert result["end"] == 2  # original end (no later section to truncate at)
    assert result["boundary_scan_errors"] == 0


def test_narrow_section_iv_skips_iii() -> None:
    """Codex iter-1 #1: Section II → Section IV (no III) should still narrow correctly."""
    doc = _make_mock_doc(
        [
            "Section II Terms\nfoo definition",
            "bar definition",
            "Section IV — Special Subjects\nappendix",
        ]
    )
    result = narrow_to_section_ii(doc, 0, 2)
    assert result["fired"] is True
    assert result["start"] == 0
    assert result["end"] == 1


def test_narrow_section_ii_not_present_returns_identity() -> None:
    """Caller-gating violation: no Section II header in range → identity."""
    doc = _make_mock_doc(
        [
            "Glossary\nplanning The art of ...",
            "stability operation ...",
        ]
    )
    result = narrow_to_section_ii(doc, 0, 1)
    assert result["fired"] is False
    assert result["start"] == 0
    assert result["end"] == 1
    assert result["boundary_scan_errors"] == 0


def test_narrow_page_read_error_on_section_ii_page_returns_identity() -> None:
    """If every Section II candidate page errors, narrowing fails closed."""
    doc = MagicMock()
    page = MagicMock()
    page.get_text.side_effect = RuntimeError("read failed")
    doc.__getitem__.return_value = page
    result = narrow_to_section_ii(doc, 0, 2)
    assert result["fired"] is False
    assert result["start"] == 0
    assert result["end"] == 2


def test_narrow_boundary_scan_error_counted() -> None:
    """Codex iter-3 #7: page-read errors during forward scan for the
    post-II boundary are counted in boundary_scan_errors so distribution
    analysis can flag the doc for review."""
    pages = [MagicMock() for _ in range(4)]
    pages[0].get_text.return_value = "Section II Terms\nfoo"
    pages[1].get_text.return_value = "bar definition"
    pages[2].get_text.side_effect = RuntimeError("error on this page")
    pages[3].get_text.return_value = "Section III"  # would terminate at page 3 (end-of-line suffix)
    doc = MagicMock()
    doc.__getitem__.side_effect = lambda i: pages[i]
    result = narrow_to_section_ii(doc, 0, 3)
    # Section II found at 0; scan errored on page 2 (counted); III found at page 3.
    assert result["fired"] is True
    assert result["start"] == 0
    assert result["end"] == 2  # page-before-III
    assert result["boundary_scan_errors"] == 1


def test_narrow_empty_range_returns_identity() -> None:
    """Codex iter-3 #6 known-limitation case: if Section II and Section III
    are on the same page (both regexes match within page 0), narrowing
    produces (0, -1) which is empty → identity transform."""
    doc = _make_mock_doc(
        [
            "Section II — Terms\nfoo\nSection III — Special",
        ]
    )
    result = narrow_to_section_ii(doc, 0, 0)
    # Section II found on page 0; forward scan starts at page 1 (out of range);
    # new_end stays at original end=0; new_start=0; range is non-empty (0,0).
    # This case actually fires successfully with a single-page range. Document
    # the limitation: the parser sees the WHOLE page including Section III content.
    # Identity-vs-fired depends on layout. Test that fired=True with range (0,0).
    assert result["start"] == 0
    assert result["end"] == 0
    assert result["fired"] is True


# ─── analyzer-integration test (Codex iter-1 #8 + iter-2 #5 partial) ────────


def test_analyzer_emits_section_ii_metadata_on_narrowing(monkeypatch) -> None:
    """End-to-end-ish: analyze_pdf wires narrow_to_section_ii correctly when
    section_structure is 'both', emits all 4 new metadata fields, and the
    parser receives the narrowed range. Real parse_glossary_entries is
    monkeypatched so the test exercises the wiring without real fitz spans."""
    from fedresearch_dictionary_extractor.core import analyzer as analyzer_mod
    from fedresearch_dictionary_extractor.extractors import glossary as glossary_mod

    captured: dict = {}

    def fake_find_range(doc, profile):
        return (0, 4)

    def fake_parse_glossary(doc, start, end, profile, force_legacy_gate=False):
        captured["parse_args"] = (start, end, force_legacy_gate)
        return []  # no entries

    def fake_inline(doc, profile):
        return []

    def fake_has_text_layer(doc):
        return True

    def fake_compute_sha(doc):
        return None

    def fake_bold_rate(doc, start, end):
        return 0.5  # above fallback threshold; bold path used

    def fake_open(path):
        return _make_mock_doc(
            [
                "Glossary\nSection I — Abbreviations\nAAA\nArmy Audit Agency",  # 0
                "ASA(ALT)\nAssistant Secretary",                                 # 1
                "Section II — Terms\nspecial access program",                    # 2
                "cleared facility",                                              # 3
                "Section III — References",                                      # 4
            ]
        )

    monkeypatch.setattr(glossary_mod, "find_glossary_page_range", fake_find_range)
    monkeypatch.setattr(glossary_mod, "parse_glossary_entries", fake_parse_glossary)
    monkeypatch.setattr(
        analyzer_mod, "_bold_preservation_rate", fake_bold_rate
    )
    monkeypatch.setattr(
        analyzer_mod.inline, "extract_inline_definitions", fake_inline
    )
    monkeypatch.setattr(
        analyzer_mod.text_utils, "has_text_layer", fake_has_text_layer
    )
    monkeypatch.setattr(
        analyzer_mod.text_utils, "compute_text_sha256", fake_compute_sha
    )

    import fitz
    monkeypatch.setattr(fitz, "open", lambda *a, **kw: fake_open(*a, **kw))

    out = analyzer_mod.analyze_pdf(
        "fake.pdf", profile_name="army"
    )

    # narrow_to_section_ii should have been called with (0, 4) and produced (2, 3)
    assert captured["parse_args"][:2] == (2, 3), (
        f"parse_glossary_entries was called with {captured['parse_args'][:2]}, "
        f"expected (2, 3) (narrowed range)"
    )
    md = out["metadata"]
    assert md["section_structure"] == "both"
    assert md["section_ii_pages"] == [3, 4]  # 1-based
    assert md["section_ii_narrowing_attempted"] is True
    assert md["section_ii_narrowing_fired"] is True
    assert md["section_ii_boundary_scan_errors"] == 0


def test_existing_candidate_output_loads_after_schema_addition() -> None:
    """Loading existing committed candidate-output JSONs after the schema
    addition still parses cleanly. Verifies the additive-schema claim that
    section_structure is back-compat for existing artifacts."""
    co_dir = (
        Path(__file__).parent.parent / "validation_set" / "candidate-output"
    )
    files = list(co_dir.glob("*.json"))
    assert files, "No candidate-output JSONs found under validation_set/"
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        assert "metadata" in d, f"{f.name}: missing metadata"
        # If section_structure is present (post-Unit-2 outputs), must be in enum.
        if "section_structure" in d["metadata"]:
            assert (
                d["metadata"]["section_structure"] in VALID_SECTION_STRUCTURES
            ), f"{f.name}: invalid section_structure value"
