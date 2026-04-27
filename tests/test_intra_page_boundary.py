"""Tests for intra-page Section II boundary filter (PR-A v0.3.0 fix #3).

Background: Unit 3 of v0.2.0 added page-level Section II range scoping. When
a single page contains BOTH a Section I tail (top of page) AND the Section II
header (middle of page), the page-level filter passes the entire page through —
the Section I acronyms above the header bleed into the extracted Section II
glossary as residue. ~15% extraction noise on AR 380-381 page 88.

Fix #3 layers a line-level filter on the FIRST page of the narrowed Section II
range: scan the page's spans, find the Section II header line, drop spans whose
Y is above the header's Y. Pure addition — pages that are purely Section II
content (no header on the page) are unaffected.
"""
from __future__ import annotations

import re

from fedresearch_dictionary_extractor.extractors.glossary import (
    _filter_spans_to_below_header,
)


# ----------------------------------------------------------------------
# Test fixtures
# ----------------------------------------------------------------------


def _span(text: str, y: float, x: float = 50.0) -> dict:
    """Build a glossary-extractor-shaped span dict at the given (x, y)."""
    return {
        "bbox": [x, y, x + 100.0, y + 12.0],
        "text": text,
        "span": {
            "bbox": [x, y, x + 100.0, y + 12.0],
            "text": text,
            "font": "Times-Roman",
            "flags": 0,
            "size": 10.0,
            "color": 0,
        },
        "y_round": round(y, 0),
    }


SECTION_II_HEADER = re.compile(r"\bSection\s*(?:II|Il)\b")


# ----------------------------------------------------------------------
# Helper-level tests
# ----------------------------------------------------------------------


def test_filter_keeps_only_spans_at_or_below_header() -> None:
    """A page with Section I tail above a mid-page Section II header drops the tail."""
    spans = [
        _span("AAR — After Action Review", y=100),    # Section I tail
        _span("ABCS — Army Battle Command System", y=120),  # Section I tail
        _span("Section II", y=200),                    # the header itself
        _span("acronym — a shortened form", y=220),    # Section II body
        _span("alpha — first Greek letter", y=240),    # Section II body
    ]
    out = _filter_spans_to_below_header(spans, SECTION_II_HEADER)
    texts = [s["text"] for s in out]
    assert texts == ["Section II", "acronym — a shortened form", "alpha — first Greek letter"]


def test_filter_handles_ocr_variant_section_il() -> None:
    """OCR'd ``Il`` (capital I + lowercase L) variant is detected just like ``II``."""
    spans = [
        _span("acronym at top of page", y=100),
        _span("Section Il", y=200),  # OCR'd variant
        _span("real entry below", y=220),
    ]
    out = _filter_spans_to_below_header(spans, SECTION_II_HEADER)
    assert [s["text"] for s in out] == ["Section Il", "real entry below"]


def test_filter_no_header_returns_input_unchanged() -> None:
    """A page with no Section II header (e.g., a fully-Section-II body page) is unaffected."""
    spans = [
        _span("entry one", y=100),
        _span("entry two", y=140),
        _span("entry three", y=180),
    ]
    out = _filter_spans_to_below_header(spans, SECTION_II_HEADER)
    assert out == spans
    assert out is not spans, "Filter should return a new list, not alias the input"


def test_filter_uses_first_match_when_multiple_present() -> None:
    """Defensive: if 'Section II' appears twice on a page (header + body
    reference), the FIRST match is the boundary — body spans below the
    second match should not be dropped.
    """
    spans = [
        _span("Section I tail", y=50),
        _span("Section II", y=100),                          # the real header
        _span("body entry referencing Section II later", y=200),  # body with the substring
        _span("more body", y=220),
    ]
    out = _filter_spans_to_below_header(spans, SECTION_II_HEADER)
    assert [s["text"] for s in out] == [
        "Section II",
        "body entry referencing Section II later",
        "more body",
    ]


def test_filter_empty_input() -> None:
    """Empty input → empty output (no error)."""
    assert _filter_spans_to_below_header([], SECTION_II_HEADER) == []
