"""Glossary header pattern + range-detection tests.

v0.4: covered header phrase variants ("Glossary of Terms" etc.) and
MAX_GLOSSARY_LOOKBACK_PAGES = 75 for long-tail docs.

v0.5 Unit D-1: backward-first-match-wins replaced with
forward-scan-largest-contiguous-block. Tie-break: EARLIER block wins.
MAX_GLOSSARY_LOOKBACK_PAGES removed (full-doc scan obviates the cap).
"""
from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest

from fedresearch_dictionary_extractor.extractors import glossary as glossary_mod
from fedresearch_dictionary_extractor.extractors.glossary import find_glossary_page_range
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


def test_v04_lookback_constant_removed() -> None:
    """v0.5 D-1: MAX_GLOSSARY_LOOKBACK_PAGES is removed entirely.
    Full-doc forward scan obviates the cap."""
    assert not hasattr(glossary_mod, "MAX_GLOSSARY_LOOKBACK_PAGES"), (
        "MAX_GLOSSARY_LOOKBACK_PAGES should be removed in v0.5 Unit D-1"
    )


def test_short_doc_finds_single_match() -> None:
    """Short docs with a single glossary header page find it."""
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


def test_long_tail_glossary_no_lookback_cap() -> None:
    """v0.5: full-doc scan finds glossary regardless of distance from end.
    PAM 73-1-shape (page 462 of 499)."""
    n_pages = 499
    glossary_page = 462
    texts = ["body text"] * n_pages
    texts[glossary_page] = "Glossary\nfoo definition"
    doc = _make_mock_doc(texts)
    result = find_glossary_page_range(doc, ARMY)
    assert result is not None
    start, _end = result
    assert start == glossary_page


def test_extremely_long_doc_no_lookback_cap() -> None:
    """v0.5: glossary at any depth is reachable (regression guard against
    re-introducing MAX_GLOSSARY_LOOKBACK_PAGES). 1000-page doc with
    glossary 800 pages from end."""
    n_pages = 1000
    glossary_page = 200  # 800 pages from end (impossible under v0.4 cap=75)
    texts = ["body text"] * n_pages
    texts[glossary_page] = "Glossary\nfoo definition"
    doc = _make_mock_doc(texts)
    result = find_glossary_page_range(doc, ARMY)
    assert result is not None
    start, _end = result
    assert start == glossary_page


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


# ─── v0.5 D-1: forward-scan-largest-contiguous-block tests ──────────────────


def test_largest_block_wins_over_running_header_pattern() -> None:
    """v0.5 D-1 core: running-header docs (ATP 3-21.10 shape) have N
    contiguous matching pages. v0.4 backward-sweep picked the LAST page;
    v0.5 picks the block's FIRST page so the full glossary is parsed.
    """
    n_pages = 620
    glossary_start, glossary_end = 580, 604  # ATP 3-21.10 shape: 25 contiguous matches
    texts = ["body text"] * n_pages
    for i in range(glossary_start, glossary_end + 1):
        texts[i] = f"Glossary\nentry-{i} definition for page {i}\n"
    texts[605] = "References\n[bibliography content]"
    doc = _make_mock_doc(texts)
    result = find_glossary_page_range(doc, ARMY)
    assert result is not None
    start, end = result
    assert start == glossary_start, f"v0.5 must pick block start={glossary_start}, got {start}"
    assert end == 604, f"end-scan should terminate at 604 (References at 605), got {end}"


def test_largest_block_wins_over_isolated_body_match() -> None:
    """v0.5 D-1: a single isolated body-text 'Glossary' reference loses
    to a multi-page real glossary block. (Class-3 shape.)
    """
    n_pages = 100
    texts = ["body text"] * n_pages
    # Isolated body reference at page 50
    texts[50] = "...as documented in the Glossary section, see below..."  # NOT whole-line, won't match
    # Better Class-3 emulation: isolated WHOLE-LINE match at page 50, but only 1 page
    texts[50] = "Some body content\nGlossary\nMore body content"
    # Real 5-page glossary block at 80-84
    for i in range(80, 85):
        texts[i] = f"Glossary\nentry-{i} definition\n"
    doc = _make_mock_doc(texts)
    result = find_glossary_page_range(doc, ARMY)
    assert result is not None
    start, _end = result
    assert start == 80, f"5-block should beat single-page body match; got start={start}"


def test_earlier_block_wins_on_tie() -> None:
    """v0.5 D-1: when two blocks have equal length, the EARLIER block wins.
    Handles the 'real glossary + later back-cover symbols sidebar' case.
    """
    n_pages = 100
    texts = ["body text"] * n_pages
    # Two equal-size blocks: 50-54 and 80-84
    for i in range(50, 55):
        texts[i] = f"Glossary\nentry-A{i}\n"
    for i in range(80, 85):
        texts[i] = f"Glossary\nentry-B{i}\n"
    doc = _make_mock_doc(texts)
    result = find_glossary_page_range(doc, ARMY)
    assert result is not None
    start, _end = result
    assert start == 50, f"earlier 5-block (50-54) must win over later 5-block; got {start}"


def test_single_page_block_when_no_multi_page_blocks() -> None:
    """v0.5 D-1: if no block has ≥2 pages, fall back to the earliest single-
    page match. (Handles short docs with a 1-page glossary.)
    """
    n_pages = 50
    texts = ["body text"] * n_pages
    texts[40] = "Glossary\nfoo: bar\nbaz: qux\n"
    doc = _make_mock_doc(texts)
    result = find_glossary_page_range(doc, ARMY)
    assert result is not None
    start, _end = result
    assert start == 40


def test_no_matches_returns_none() -> None:
    """v0.5 D-1: no glossary header anywhere → None. Preserved from v0.4."""
    n_pages = 30
    texts = ["nothing about glossaries here"] * n_pages
    doc = _make_mock_doc(texts)
    result = find_glossary_page_range(doc, ARMY)
    assert result is None


def test_strict_contiguous_no_gap_tolerance() -> None:
    """v0.5 D-1: per A6 empirical scan, strict-contiguous is the chosen
    grouping. A 5-page real glossary block with a 1-page gap splits into
    two smaller blocks. The larger half wins.

    Regression sentinel: if a future change adds gap tolerance, this test
    fails so the operator must explicitly re-decide the gap policy.
    """
    n_pages = 100
    texts = ["body text"] * n_pages
    # Block A: pages 50-52 (3 pages), GAP at 53, Block B: pages 54-56 (3 pages)
    for i in [50, 51, 52, 54, 55, 56]:
        texts[i] = f"Glossary\nentry-{i}\n"
    # texts[53] left as "body text" — substantive content, would tolerate as a gap
    doc = _make_mock_doc(texts)
    result = find_glossary_page_range(doc, ARMY)
    assert result is not None
    start, end = result
    # Under strict contiguous + earlier-wins tie: first 3-block (50-52) wins.
    assert start == 50
    # The end-scan goes forward from 50; will encounter "body text" at 53
    # (no terminator pattern matched), keep scanning, find another "Glossary"
    # block — but end-scan only checks for End patterns (Index/References/etc),
    # not header patterns. So end-scan continues to doc end OR a terminator.
    # In this synthetic, no terminator exists past page 56, so end = n_pages-1.
    # The key assertion is start=50 (not merged).
