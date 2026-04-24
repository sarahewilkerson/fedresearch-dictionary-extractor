"""Pipeline integration test (P1) — v0.2.a.

Exercises the REAL reject→accumulate→flush→strip path through the
extractor's term-validation state machine, NOT a _flush-only shortcut.

The plan's safety case for the v0.2.a pattern depends on the interaction
between:
  1. `_validate_term` returning False at glossary.py:359
  2. The rejected line appending to `current_def_lines` at line 363
  3. Subsequent `_flush` running `strip_citations` at line 516

A _flush-only test would bypass steps 1-2. This test mocks the fitz page
interface just enough to drive the real `parse_glossary_entries` loop, so
the whole handoff is covered.

Plan: docs/plans/2026-04-24-invalid-term-blocklist.md (§3c, §6 P1)
"""
from __future__ import annotations

from unittest.mock import MagicMock

from fedresearch_dictionary_extractor.extractors.glossary import parse_glossary_entries
from fedresearch_dictionary_extractor.profiles.army import ArmyProfile


def _span(text: str, bbox: tuple[float, float, float, float], bold: bool = False) -> dict:
    """Minimal fitz-style span dict compatible with glossary.parse_glossary_entries."""
    return {
        "bbox": list(bbox),
        "text": text,
        "font": "Times-Bold" if bold else "Times-Roman",
        "flags": 16 if bold else 0,  # fitz FLAGS bold bit
        "size": 10.0,
        "color": 0,
    }


def _page_dict_from_lines(lines: list[tuple[float, list[dict]]]) -> dict:
    """Build a fitz `page.get_text("dict")` response from (y, [spans]) pairs.

    Each pair is a distinct visual line (distinct y). Blocks are synthetic
    but match the shape the extractor reads (block → lines → spans).
    """
    fitz_lines = []
    for y, spans in lines:
        for sp in spans:
            sp["bbox"][1] = y
            sp["bbox"][3] = y + 12.0
        fitz_lines.append({"spans": spans})
    return {"blocks": [{"lines": fitz_lines}]}


def _mock_page(page_dict: dict, height: float = 792.0) -> MagicMock:
    page = MagicMock()
    page.get_text.return_value = page_dict
    page.rect.height = height
    page.get_label.return_value = None
    return page


def _mock_doc(pages: list[MagicMock]) -> MagicMock:
    doc = MagicMock()
    doc.__len__.return_value = len(pages)
    doc.__getitem__.side_effect = lambda i: pages[i]
    return doc


def test_p1_ar_fragment_rejected_and_citation_stripped() -> None:
    """Full reject→accumulate→flush→strip over synthetic AR_135-100-p77-like flow.

    Input flow (all lines in the term column at x=50, which gives
    term_col_threshold > 50):
      line 1:  BOLD "Entry on duty date"       ← valid new term
      line 2:  ROMAN "The date travel officially begins (per compete"
      line 3:  ROMAN "orders). The official travel date is determined "
      line 4:  ROMAN "by the mode. (AR 135 200 and"
      line 5:  BOLD "AR 124"                   ← new-term candidate, REJECTED by v0.2.a pattern
      line 6:  ROMAN "210)"                    ← continuation
      line 7:  BOLD "Equipment concentration site"  ← valid new term (flushes the previous)

    Expected: "Entry on duty date" is emitted with a definition that, after
    strip_citations, no longer contains the "(AR 135 200 and AR 124 210)"
    parenthetical because it forms a valid multi-pub citation.
    """
    # All x-coords in the term column (50-something) — term_col_threshold is
    # min_x + TERM_COL_MARGIN (30). min_x=50 → threshold=80. All our spans
    # start at 50, so all are "in term column" → bold spans become new-term
    # candidates, non-bold continuations fall to the continuation branch.
    x = 50.0  # noqa: N806 — uppercase elsewhere would shadow; this is a local coordinate
    page_dict = _page_dict_from_lines(
        [
            (200.0, [_span("Entry on duty date", (x, 0, 250, 0), bold=True)]),
            (220.0, [_span("The date travel officially begins (per compete", (x, 0, 400, 0))]),
            (240.0, [_span("orders). The official travel date is determined", (x, 0, 400, 0))]),
            (260.0, [_span("by the mode. (AR 135 200 and", (x, 0, 400, 0))]),
            (280.0, [_span("AR 124", (x, 0, 100, 0), bold=True)]),       # REJECTED by new pattern
            (300.0, [_span("210)", (x, 0, 100, 0))]),                     # continuation
            (320.0, [_span("Equipment concentration site", (x, 0, 300, 0), bold=True)]),
            (340.0, [_span("An equipment storage area.", (x, 0, 300, 0))]),
        ]
    )
    pages = [_mock_page(page_dict)]
    doc = _mock_doc(pages)

    profile = ArmyProfile()
    entries = parse_glossary_entries(doc, 0, 0, profile)

    terms = [e["term"] for e in entries]
    # Primary assertion: AR 124 was rejected, not emitted
    assert "AR 124" not in terms, f"pattern failed to reject AR 124; got terms: {terms}"
    # Primary assertion: Entry on duty date was emitted
    assert "Entry on duty date" in terms, f"missing Entry on duty date; got: {terms}"
    # Primary assertion: Equipment concentration site was emitted after
    assert "Equipment concentration site" in terms, f"missing ECS; got: {terms}"

    # Byte-exact assertion on the cleaned definition (Codex iter-1 P3 —
    # catches over-stripping or truncation that the absence-only checks
    # below would miss).
    eod = next(e for e in entries if e["term"] == "Entry on duty date")
    expected_def = (
        "The date travel officially begins (per compete orders). "
        "The official travel date is determined by the mode."
    )
    assert eod["definition"] == expected_def, (
        f"Entry on duty date def not cleaned as expected.\n"
        f"  expected: {expected_def!r}\n"
        f"  actual:   {eod['definition']!r}"
    )

    # Absence assertions (belt-and-suspenders — the byte-exact check above
    # already catches these, but leaving them as explicit guards against
    # future test refactors that might relax the exact match).
    assert "AR 124" not in eod["definition"]
    assert "210)" not in eod["definition"]


def test_p1_legitimate_ar_hyphenated_still_stripped() -> None:
    """Regression: full '(AR 124-210)' citation still matches strip_citations."""
    x = 50.0  # noqa: N806 — uppercase elsewhere would shadow; this is a local coordinate
    page_dict = _page_dict_from_lines(
        [
            (200.0, [_span("Term A", (x, 0, 100, 0), bold=True)]),
            (220.0, [_span("Body text referring to (AR 124-210) publication.", (x, 0, 500, 0))]),
            (240.0, [_span("Term B", (x, 0, 100, 0), bold=True)]),
            (260.0, [_span("Other body.", (x, 0, 300, 0))]),
        ]
    )
    pages = [_mock_page(page_dict)]
    doc = _mock_doc(pages)

    profile = ArmyProfile()
    entries = parse_glossary_entries(doc, 0, 0, profile)

    term_a = next(e for e in entries if e["term"] == "Term A")
    # strip_citations removes the (AR 124-210) parenthetical entirely
    assert "AR 124-210" not in term_a["definition"], \
        f"full citation not stripped: {term_a['definition']!r}"
