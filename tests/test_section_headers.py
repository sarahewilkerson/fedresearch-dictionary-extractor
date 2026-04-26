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
)
from fedresearch_dictionary_extractor.profiles import get_profile
from fedresearch_dictionary_extractor.profiles.army import (
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
