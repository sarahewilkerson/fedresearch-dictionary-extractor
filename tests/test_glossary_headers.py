"""Glossary header pattern + lookback tests (v0.4.0).

Verifies that the ArmyProfile.glossary_header_patterns accept the
"Glossary of {Terms,Acronyms,Abbreviations}" phrase variants observed in
~70% of v0.3.0 zero-entry-with-glossary failures, and that
MAX_GLOSSARY_LOOKBACK_PAGES = 75 catches the long-tail layout exhibited
by PAM 73-1 (glossary at page 462 of 499).
"""
from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest

from fedresearch_dictionary_extractor.extractors.glossary import (
    MAX_GLOSSARY_LOOKBACK_PAGES,
    find_glossary_page_range,
)
from fedresearch_dictionary_extractor.profiles import get_profile

ARMY = get_profile("army")


# ─── Pattern-level tests ────────────────────────────────────────────────────


def _compile_header_alternation() -> re.Pattern:
    """Mirrors find_glossary_page_range's compilation:
    each pattern compiled with re.IGNORECASE | re.MULTILINE; we test the
    union since any-match accepts the page."""
    return re.compile(
        "|".join(f"(?:{p})" for p in ARMY.glossary_header_patterns),
        re.IGNORECASE | re.MULTILINE,
    )


HEADER_POSITIVE = [
    # Existing v0.3.0 patterns (regression-guard)
    "Glossary",
    "GLOSSARY",
    "Section II — Terms",
    "Terms and Abbreviations",
    "Acronyms and Abbreviations",
    # v0.4.0 additions — "Glossary of …" phrase
    "Glossary of Terms",
    "Glossary of Term",
    "Glossary of Acronyms",
    "Glossary of Acronym",
    "Glossary of Abbreviations",
    "Glossary of Abbreviation",
    "Glossary of Terms and Abbreviations",
    "Glossary of Acronyms and Abbreviations",
    "GLOSSARY OF TERMS",
    "GLOSSARY OF ACRONYMS",
    "GLOSSARY OF TERMS AND ABBREVIATIONS",
    # Mixed leading whitespace, case-insensitive
    "  Glossary of Terms  ",
    "glossary of terms",
]

HEADER_NEGATIVE = [
    # Body-text references — must not match
    "see the Glossary of Terms for details",
    "the Glossary of Terms section contains",
    # Off-pattern variants
    "Glossary Reference",
    "Glossary 1",
    "Glossary of Operations",        # not in our enumerated phrase set
    "Glossary of Symbols",           # not in our set
    "References",
    "Index",
]


@pytest.mark.parametrize("s", HEADER_POSITIVE)
def test_glossary_header_matches(s: str) -> None:
    pat = _compile_header_alternation()
    assert pat.search(s), f"glossary header should match: {s!r}"


@pytest.mark.parametrize("s", HEADER_NEGATIVE)
def test_glossary_header_rejects(s: str) -> None:
    pat = _compile_header_alternation()
    assert not pat.search(s), f"glossary header should NOT match: {s!r}"


# ─── Lookback distance tests ────────────────────────────────────────────────


def _make_mock_doc(page_texts: list[str]) -> MagicMock:
    pages = []
    for txt in page_texts:
        page = MagicMock()
        page.get_text.return_value = txt
        pages.append(page)
    doc = MagicMock()
    doc.__getitem__.side_effect = lambda i: pages[i]
    doc.__len__.return_value = len(pages)
    return doc


def test_lookback_constant_is_75() -> None:
    """Pin the lookback constant — regression guard for the v0.4.0 bump
    from 30 to 75. If a future change lowers this without updating the
    failing cohort's expected fix, surface it loudly."""
    assert MAX_GLOSSARY_LOOKBACK_PAGES == 75


def test_lookback_reaches_pam_73_1_layout() -> None:
    """PAM 73-1 has total=499 pages with glossary at page 462 — 37 pages
    from the end. v0.3.0 (lookback=30) missed it. v0.4.0 (lookback=75)
    must reach it."""
    n_pages = 499
    glossary_page = 462
    texts = ["body text"] * n_pages
    texts[glossary_page] = "Glossary\nfoo definition"
    doc = _make_mock_doc(texts)
    result = find_glossary_page_range(doc, ARMY)
    assert result is not None
    start, _end = result
    assert start == glossary_page


def test_lookback_short_doc_unaffected() -> None:
    """Short docs (< lookback) continue to work as before."""
    texts = [
        "Cover page",
        "Chapter 1",
        "Chapter 2",
        "Glossary of Terms\nfoo definition",
        "References",
    ]
    doc = _make_mock_doc(texts)
    result = find_glossary_page_range(doc, ARMY)
    assert result is not None
    start, _end = result
    assert start == 3


def test_lookback_does_not_reach_beyond_75() -> None:
    """Doc with glossary at page N-76 (one beyond the lookback window)
    is NOT found. Pin the bound to catch unintended lookback growth."""
    n_pages = 200
    glossary_page = n_pages - 76 - 1  # 76 pages from end (just past window)
    texts = ["body text"] * n_pages
    texts[glossary_page] = "Glossary\nfoo definition"
    doc = _make_mock_doc(texts)
    result = find_glossary_page_range(doc, ARMY)
    assert result is None


def test_long_tail_glossary_of_terms() -> None:
    """Composite: deep-doc layout AND 'Glossary of Terms' phrase header.
    Mirrors AR 420-1 (427 pages, glossary at page 392 = 35 from end)."""
    n_pages = 427
    glossary_page = 392
    texts = ["chapter body"] * n_pages
    texts[glossary_page] = "Glossary of Terms\nfoo definition"
    doc = _make_mock_doc(texts)
    result = find_glossary_page_range(doc, ARMY)
    assert result is not None
    start, _end = result
    assert start == glossary_page
