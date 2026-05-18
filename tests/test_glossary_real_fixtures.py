"""v0.5 D-1: realistic-PDF text fixture tests.

Loads `tests/fixtures/glossary_range_v05/*.json` (real `page.get_text("text")`
output captured from prod PDFs) and asserts that find_glossary_page_range
produces the expected v0.5 ranges. Distinct from the synthetic mock-doc tests
in test_glossary_headers.py because real PDFs have actual OCR-derived
whitespace, formatting, and edge-case characters.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from fedresearch_dictionary_extractor.extractors.glossary import find_glossary_page_range
from fedresearch_dictionary_extractor.profiles import get_profile

ARMY = get_profile("army")
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "glossary_range_v05"


def _load_fixture(name: str) -> tuple[MagicMock, dict]:
    """Load a fixture JSON and return a fitz-compatible mock doc + metadata.

    Pages outside the captured range return empty text (so find_glossary_page_range
    can full-scan the conceptual doc — uncaptured pages are guaranteed not to
    contain header matches because they're empty strings).
    """
    payload = json.loads((FIXTURE_DIR / f"{name}.json").read_text())
    total = payload["total_pages_in_pdf"]
    pages_dict: dict[int, str] = {int(k): v for k, v in payload["pages"].items()}

    page_mocks = []
    for i in range(total):
        page = MagicMock()
        page.get_text.return_value = pages_dict.get(i, "")
        page_mocks.append(page)
    doc = MagicMock()
    doc.__getitem__.side_effect = lambda i: page_mocks[i]
    doc.__len__.return_value = total
    return doc, payload


def test_atp_3_21_10_finds_block_580_through_604() -> None:
    """ATP 3-21.10 (Class-2 prototype): running-header doc with "Glossary" on
    every page from 580 to 604. v0.4 returned (604, 605); v0.5 must return
    a range starting at 580."""
    doc, meta = _load_fixture("atp-3-21-10")
    result = find_glossary_page_range(doc, ARMY)
    assert result is not None
    start, end = result
    assert start == 580, f"v0.5 must find block start at 580, got {start}"
    # End may extend depending on what end-scan finds after 604; just assert
    # it includes the block.
    assert end >= 604, f"end must include the block end (604+), got {end}"


def test_ar_12_15_finds_earlier_block_not_body_reference() -> None:
    """AR 12-15 (Class-3 prototype): v0.4 returned (343, 343) for an
    isolated body-text reference. v0.5 must find the earlier real
    glossary section (per Unit 0 measurements, loose heuristic = (21, 21))."""
    doc, meta = _load_fixture("ar-12-15")
    result = find_glossary_page_range(doc, ARMY)
    assert result is not None
    start, _end = result
    assert start < 50, (
        f"v0.5 must find an earlier glossary section, not the page-343 "
        f"body reference v0.4 picked. Got start={start}."
    )


def test_ar_11_7_front_matter_no_false_positive() -> None:
    """AR 11-7 is a validation-set doc that worked under v0.4. v0.5's
    full-doc scan must not regress by picking up a front-matter TOC
    reference. This is a regression sentinel for the broader 31-doc
    validation set."""
    doc, meta = _load_fixture("ar-11-7")
    result = find_glossary_page_range(doc, ARMY)
    # The fixture captures pages 0-31 only; result must either return None
    # (no match in front-matter, real glossary is elsewhere in uncaptured
    # pages) OR a non-front-matter match (>0). The KEY assertion: any match
    # must be on a page with substantive glossary content, not a TOC dot-
    # leader line. We assert: if a result is returned, the matched start
    # page text must NOT be dominated by dot-leaders.
    if result is not None:
        start, _end = result
        page_text = doc[start].get_text("text")
        # TOC pages have many "....." runs; real glossary headers don't.
        dot_runs = page_text.count("....")
        assert dot_runs < 5, (
            f"page {start} looks like a TOC line (dot-leaders count={dot_runs}); "
            f"v0.5 must not pick TOC false-positives. Page text excerpt: "
            f"{page_text[:200]!r}"
        )


def test_standalone_terminator_in_glossary_does_not_truncate_end_scan() -> None:
    """v0.5 D-1 Hard 30% §H2: when start moves earlier (full-glossary range),
    end-scan crosses more pages and may encounter standalone terminator
    words ("References", "Appendix") inside the glossary section as part
    of definition text.

    Verify the existing end-pattern whole-line anchoring handles this
    correctly using the ATP 3-21.10 fixture: the glossary contains
    definitions referring to terms like "Appendix" but the end-scan must
    NOT truncate inside the glossary."""
    doc, meta = _load_fixture("atp-3-21-10")
    result = find_glossary_page_range(doc, ARMY)
    assert result is not None
    start, end = result
    # The block at 580-604 must be preserved; end-scan should not cut
    # inside it.
    assert end >= 604, (
        f"end-scan truncated inside glossary range (got end={end} < 604); "
        f"standalone terminator-as-glossary-term broke end-detection."
    )
