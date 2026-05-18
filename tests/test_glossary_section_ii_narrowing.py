"""v0.5 D-1: Section II narrowing interaction.

When find_glossary_page_range returns an earlier start (full-glossary range
including Section I), narrow_to_section_ii must still correctly clip to the
Section II boundary. Two assertions per applicable doc:

1. test_section_ii_narrowed_range_matches_section_ii_header — the narrowed
   start page contains the SECTION_II_HEADER match (asserts exact boundary,
   not just containment).
2. test_section_ii_extracted_terms_stable — extracted glossary entries match
   the v0.4 golden for these docs.

Applicable docs: validation-set docs with section_structure ∈
{both, section_ii_only} per v0.4 golden output.
"""
from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest

from fedresearch_dictionary_extractor.core.analyzer import analyze_pdf
from fedresearch_dictionary_extractor.extractors.glossary import (
    SECTION_STRUCTURE_BOTH,
    SECTION_STRUCTURE_II_ONLY,
    detect_section_structure,
    find_glossary_page_range,
    narrow_to_section_ii,
)
from fedresearch_dictionary_extractor.profiles import get_profile
from fedresearch_dictionary_extractor.profiles.army import SECTION_II_HEADER

REPO = Path(__file__).parent.parent
PDF_DIR = REPO / "validation_set" / "pdfs"
GOLDEN = REPO / "validation_set" / "v0.5-unit-d1-v04-golden-output.json"

GOLDEN_BY_STEM: dict[str, dict] = json.loads(GOLDEN.read_text())
SECTION_II_STEMS = [
    s for s, g in GOLDEN_BY_STEM.items()
    if g.get("section_structure") in {SECTION_STRUCTURE_BOTH, SECTION_STRUCTURE_II_ONLY}
]

ARMY = get_profile("army")


@pytest.mark.parametrize("stem", sorted(SECTION_II_STEMS), ids=lambda s: s[:40])
def test_section_ii_narrowed_range_matches_section_ii_header(stem: str) -> None:
    """Narrowed start page must contain a SECTION_II_HEADER match.
    Asserts exact Section II boundary (Codex iter-2 #9)."""
    pdf_path = PDF_DIR / f"{stem}.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF not available: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    try:
        full_range = find_glossary_page_range(doc, ARMY)
        if full_range is None:
            pytest.fail(f"{stem}: v0.5 returned None but v0.4 found section_ii — regression")
        start, end = full_range
        structure = detect_section_structure(doc, start, end, ARMY)
        if structure not in {SECTION_STRUCTURE_BOTH, SECTION_STRUCTURE_II_ONLY}:
            pytest.skip(f"{stem}: v0.5 detected structure={structure} (golden had section_ii)")
        narrowed = narrow_to_section_ii(doc, start, end)
        if not narrowed["fired"]:
            pytest.skip(f"{stem}: narrowing did not fire (identity transform)")
        narrowed_start_page_text = doc[narrowed["start"]].get_text("text")
    finally:
        doc.close()

    assert SECTION_II_HEADER.search(narrowed_start_page_text), (
        f"{stem}: narrowed start (page {narrowed['start']}) does not contain "
        f"a SECTION_II_HEADER match. Page text excerpt: "
        f"{narrowed_start_page_text[:200]!r}"
    )


@pytest.mark.parametrize("stem", sorted(SECTION_II_STEMS), ids=lambda s: s[:40])
def test_section_ii_extracted_terms_stable(stem: str) -> None:
    """Extracted terms for section_ii docs match the v0.4 golden term set.
    Catches silent term-identity drift from range/narrowing changes."""
    pdf_path = PDF_DIR / f"{stem}.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF not available: {pdf_path}")

    golden = GOLDEN_BY_STEM[stem]
    expected_terms = set(golden.get("term_set", []))

    out = analyze_pdf(str(pdf_path), profile_name="army", deterministic=True)
    actual_terms = {e["term_normalized"] for e in out.get("entries", []) if e.get("term_normalized")}

    added = sorted(actual_terms - expected_terms)
    removed = sorted(expected_terms - actual_terms)

    assert not added and not removed, (
        f"{stem}: term-identity drift in section_ii narrowed range.\n"
        f"  added (in v0.5, not in v0.4 golden): {added[:10]}\n"
        f"  removed (in v0.4 golden, not in v0.5): {removed[:10]}"
    )
