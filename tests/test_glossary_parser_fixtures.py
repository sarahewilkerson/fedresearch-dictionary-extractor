"""v0.5 D-2: fixture loader + reproducibility harness.

For each per-class fixture in tests/fixtures/glossary_parser_v0.5/, load
the captured page-dict payload into a mock fitz.Document, run
parse_glossary_entries, and assert the symptom (0 entries) is reproduced.

This is the harness future D-3-X units use to verify their fixes against
the original failure-mode without needing the source PDF.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fedresearch_dictionary_extractor.core.analyzer import (
    analyze_pdf,  # noqa: F401 — for completeness
)
from fedresearch_dictionary_extractor.extractors.glossary import (
    parse_glossary_entries,
)
from fedresearch_dictionary_extractor.profiles import get_profile
from fedresearch_dictionary_extractor.profiles.army import SECTION_II_HEADER

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "glossary_parser_v0.5"
ARMY = get_profile("army")
FIXTURE_FILES = sorted(FIXTURE_DIR.glob("*.json"))


def _make_mock_doc(fixture: dict) -> MagicMock:
    """Reconstruct a fitz-Document-like object from the captured page payloads."""
    total = fixture["total_pages"]
    page_data: dict[int, dict] = {int(k): v for k, v in fixture["pages"].items()}

    page_mocks = []
    for i in range(total):
        page = MagicMock()
        if i in page_data:
            page.get_text.side_effect = lambda fmt="text", _i=i: (
                page_data[_i]["page_dict"] if fmt == "dict" else page_data[_i]["page_text"]
            )
        else:
            page.get_text.side_effect = lambda fmt="text": (
                {"blocks": []} if fmt == "dict" else ""
            )
        page.rect = MagicMock()
        page.rect.height = 792  # standard US Letter at 72 DPI
        page.get_label = MagicMock(return_value=None)
        page_mocks.append(page)
    doc = MagicMock()
    doc.__getitem__.side_effect = lambda i: page_mocks[i]
    doc.__len__.return_value = total
    return doc


@pytest.mark.parametrize("fixture_path", FIXTURE_FILES, ids=lambda p: p.stem)
def test_fixture_reproduces_zero_entries(fixture_path: Path) -> None:
    """For each captured failure-mode fixture, parse_glossary_entries must
    return [] (reproducing the D-2 zero-entry symptom) — proves the fixture
    captured the failure faithfully."""
    fixture = json.loads(fixture_path.read_text())
    doc = _make_mock_doc(fixture)

    detected_start, detected_end = fixture["detected_range_0idx"]
    section_ii_pattern = (
        SECTION_II_HEADER if fixture["section_ii_narrowing_fired"] else None
    )

    # Use parse_glossary_entries directly with the captured detected range
    # (NOT find_glossary_page_range, which would re-detect and might differ
    # from the v0.5 production behavior captured at fixture time).
    entries = parse_glossary_entries(
        doc,
        detected_start,
        detected_end,
        ARMY,
        section_ii_header_pattern=section_ii_pattern,
    )
    assert entries == [], (
        f"{fixture_path.stem}: expected 0 entries (failure-mode reproduction); "
        f"got {len(entries)}. Fixture may have lost the failure signature."
    )


def test_fixtures_dir_has_at_least_one_per_class() -> None:
    """Sanity check: D-2 plan requires at least one fixture per named failure
    class. With 3 fixtures committed (p1-acronym-filtered, p2-footer-as-term,
    p1-p2-hybrid) we cover the 2 named classes + 1 hybrid."""
    names = {p.stem for p in FIXTURE_FILES}
    assert "p1-acronym-filtered" in names, "Class P-1 fixture missing"
    assert "p2-footer-as-term" in names, "Class P-2 fixture missing"
    assert len(FIXTURE_FILES) >= 3, f"Expected ≥3 fixtures, got {len(FIXTURE_FILES)}"
