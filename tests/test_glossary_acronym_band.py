"""v0.5 D-3-A: ACRONYM_COL_MARGIN tests.

Verify the wider acronym-band gate accepts Section I acronyms indented past
TERM_COL_MARGIN but within ACRONYM_COL_MARGIN.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from fedresearch_dictionary_extractor.extractors.glossary import (
    ACRONYM_COL_MARGIN,
    TERM_COL_MARGIN,
    parse_glossary_entries,
)
from fedresearch_dictionary_extractor.profiles import get_profile

ARMY = get_profile("army")


def _make_page_dict(spans: list[dict]) -> dict:
    """Build a minimal page.get_text('dict') payload from a list of spans."""
    return {
        "blocks": [{
            "type": 0,
            "lines": [{"spans": [s]} for s in spans],
        }],
    }


def _mock_doc(page_specs: list[list[dict]], page_height: int = 792) -> MagicMock:
    """Build a mock fitz.Document. page_specs is one list-of-spans per page."""
    pages = []
    for spans in page_specs:
        page = MagicMock()
        page_dict = _make_page_dict(spans)
        page_text = "\n".join(s.get("text", "") for s in spans)
        page.get_text.side_effect = lambda fmt="text", _pd=page_dict, _pt=page_text: (
            _pd if fmt == "dict" else _pt
        )
        page.rect = MagicMock()
        page.rect.height = page_height
        page.get_label = MagicMock(return_value=None)
        pages.append(page)
    doc = MagicMock()
    doc.__getitem__.side_effect = lambda i: pages[i]
    doc.__len__.return_value = len(pages)
    return doc


def _span(text: str, x: float, y: float, bold: bool = False) -> dict:
    """Helper to build a span dict."""
    return {
        "text": text,
        "bbox": [x, y, x + 100, y + 12],
        "font": "Arial-Bold" if bold else "Arial",
        "flags": 16 if bold else 0,
    }


# ─── Constants ─────────────────────────────────────────────────────────────


def test_acronym_col_margin_constant_is_80() -> None:
    """Pin the constant value to catch unintended drift."""
    assert ACRONYM_COL_MARGIN == 80
    assert TERM_COL_MARGIN == 30
    assert ACRONYM_COL_MARGIN > TERM_COL_MARGIN, (
        "ACRONYM_COL_MARGIN must widen the band, not narrow it"
    )


# ─── Gate behavior tests ────────────────────────────────────────────────────


def test_acronym_in_wider_band_admitted() -> None:
    """v0.5 D-3-A: an acronym-shaped line at first_x = min_x + 40 (past
    TERM_COL_MARGIN=30 but within ACRONYM_COL_MARGIN=80) is admitted.

    Synthetic page mirroring Section I acronym layout:
    - Section header "SECTION I — ACRONYMS..." at x=50 (sets min_x)
    - Acronym "ADP" at x=90 (40pt past min_x)
    - Definition "Army doctrine publication" at x=140 (continuation)
    """
    spans = [
        _span("Glossary", 50, 100, bold=True),
        _span("SECTION I — ACRONYMS AND ABBREVIATIONS", 50, 130, bold=True),
        _span("ADP", 90, 160, bold=False),
        _span("Army doctrine publication", 140, 160, bold=False),
        _span("ADRP", 90, 180, bold=False),
        _span("Army doctrine reference publication", 140, 180, bold=False),
    ]
    doc = _mock_doc([spans])
    # Use parse_glossary_entries directly with start=0, end=0
    entries = parse_glossary_entries(doc, 0, 0, ARMY)
    terms = {e["term"] for e in entries}
    # At least one of ADP / ADRP should be admitted as a term under D-3-A
    assert "ADP" in terms or "ADRP" in terms, (
        f"D-3-A should admit at least one acronym-shaped line in wider band; got terms={terms}"
    )


def test_acronym_outside_wider_band_rejected() -> None:
    """An acronym-shaped line outside the ACRONYM_COL_MARGIN band (deep indent)
    is still rejected — bounds the false-positive surface."""
    spans = [
        _span("Glossary", 50, 100, bold=True),
        _span("ADP", 200, 130, bold=False),  # x=200, far outside 50+80=130 band
        _span("Army doctrine publication", 240, 130, bold=False),
    ]
    doc = _mock_doc([spans])
    entries = parse_glossary_entries(doc, 0, 0, ARMY)
    # ADP at x=200 is outside both TERM_COL_MARGIN and ACRONYM_COL_MARGIN bands
    # (assuming min_x=50). It should NOT be admitted.
    terms = {e["term"] for e in entries}
    assert "ADP" not in terms, (
        f"acronym outside band must NOT be admitted; got terms={terms}"
    )


def test_bold_acronym_in_wider_band_also_admitted() -> None:
    """Codex iter-1 #1 regression: bold AND acronym-shaped lines outside the
    strict band must ALSO be admitted (not only non-bold acronyms)."""
    spans = [
        _span("Glossary", 50, 100, bold=True),
        _span("ADP", 90, 130, bold=True),  # bold + acronym + outside strict band
        _span("Army doctrine publication", 140, 130, bold=False),
    ]
    doc = _mock_doc([spans])
    entries = parse_glossary_entries(doc, 0, 0, ARMY)
    terms = {e["term"] for e in entries}
    assert "ADP" in terms, (
        f"bold acronym in wider band must be admitted (Codex iter-1 #1 fix); "
        f"got terms={terms}"
    )
