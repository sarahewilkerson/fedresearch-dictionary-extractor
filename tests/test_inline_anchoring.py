"""Tests for inline-extractor sentence-boundary anchoring (PR-A v0.3.0 fix #1).

Background: ``inline.py`` walks every page and runs profile-defined patterns
like ``For purposes of this regulation, X means Y.`` and ``The term 'X' means Y.``
across the page text. Until v0.3.0, those patterns were compiled with
``re.IGNORECASE``, which silently widened every ``[A-Z]`` character class to
match lowercase too. As a result, mid-sentence body fragments like
``... the term dampen usually means the muting ...`` matched, producing the
TC 1-19.30 ``dampen \\nusually`` false positive captured in
validation_set/batch1_reconciled.yaml.

Fix #1 drops ``re.IGNORECASE`` and adds a sentence-boundary lookbehind so
patterns only fire at the start of a line OR after sentence-terminal
punctuation. True positives (sentence-start "The term 'foo' means bar.")
remain extracted; mid-sentence false positives no longer match.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import fitz  # noqa: F401  — imported by the extractor
import pytest

from fedresearch_dictionary_extractor.extractors.inline import extract_inline_definitions
from fedresearch_dictionary_extractor.profiles.army import ArmyProfile


# ----------------------------------------------------------------------
# Test fixtures — minimal mock fitz.Document
# ----------------------------------------------------------------------


def _mock_doc_from_pages(page_texts: list[str]) -> MagicMock:
    """Build a fitz.Document MagicMock with one page per string."""
    doc = MagicMock()
    pages = []
    for text in page_texts:
        page = MagicMock()
        page.get_text.return_value = text
        page.get_label.return_value = None
        pages.append(page)
    doc.__len__.return_value = len(pages)
    doc.__getitem__.side_effect = lambda i: pages[i]
    return doc


@pytest.fixture
def army() -> ArmyProfile:
    return ArmyProfile()


# ----------------------------------------------------------------------
# Negative cases — false positives that v0.2.0 emitted; v0.3.0 must not
# ----------------------------------------------------------------------


def test_lowercase_mid_sentence_the_term_does_not_match(army: ArmyProfile) -> None:
    """Reproduces the TC 1-19.30 page-102 ``dampen \\nusually`` bug class.

    A body paragraph with ``the term dampen\\nusually means ...`` must NOT be
    captured. The IGNORECASE flag previously widened ``[A-Z]`` to match the
    lowercase ``d`` in ``dampen`` (and ``\\s`` consumed the newline between
    ``dampen`` and ``usually``, producing the ``"dampen \\nusually"`` term
    pinned in validation_set/batch1_reconciled.yaml).
    """
    page_text = (
        "Acoustic effects on weapons systems are well documented in the field. "
        "When a system encounters acoustic interference, the term dampen\nusually "
        "means the muting of undesirable overtones. Soldiers must understand "
        "these effects before deploying. " * 3  # padding so >50 chars
    )
    doc = _mock_doc_from_pages([page_text])
    out = extract_inline_definitions(doc, army)
    assert out == [], (
        f"Mid-sentence 'the term dampen\\nusually' must produce zero inline "
        f"matches; got {len(out)}: {[(e['term'], e['definition'][:40]) for e in out]}"
    )


def test_lowercase_mid_sentence_for_purposes_does_not_match(army: ArmyProfile) -> None:
    """Mid-sentence ``... for purposes of this regulation, ...`` must not fire."""
    page_text = (
        "This document is similar in scope to other regulations and "
        "for purposes of this regulation, foo means a generic placeholder term "
        "that should not be extracted. Additional padding text follows. " * 3
    )
    doc = _mock_doc_from_pages([page_text])
    out = extract_inline_definitions(doc, army)
    assert out == [], (
        f"Mid-sentence lowercase 'for purposes of' must produce zero inline "
        f"matches; got {len(out)}: {[(e['term'], e['definition'][:40]) for e in out]}"
    )


# ----------------------------------------------------------------------
# Positive cases — true positives that must remain extracted
# ----------------------------------------------------------------------


def test_sentence_start_for_purposes_matches(army: ArmyProfile) -> None:
    """Canonical sentence-start usage continues to be extracted."""
    page_text = (
        "Section 2. Definitions.\n\n"
        "For purposes of this regulation, Healthcare Provider means a licensed "
        "professional authorized to deliver medical services to soldiers. "
        "Additional context follows."
    )
    doc = _mock_doc_from_pages([page_text])
    out = extract_inline_definitions(doc, army)
    terms = [e["term"] for e in out]
    assert "Healthcare Provider" in terms, (
        f"Sentence-start 'For purposes of' must still match. Got: {terms}"
    )


def test_sentence_start_the_term_matches(army: ArmyProfile) -> None:
    """The 'The term X means Y' pattern at sentence start must still fire."""
    page_text = (
        "Chapter 3 of this document covers safety. "
        "The term Safety Officer means an individual designated to oversee "
        "compliance with established safety protocols on the installation."
    )
    doc = _mock_doc_from_pages([page_text])
    out = extract_inline_definitions(doc, army)
    terms = [e["term"] for e in out]
    assert "Safety Officer" in terms, (
        f"Sentence-start 'The term' must still match. Got: {terms}"
    )


def test_after_sentence_terminal_match(army: ArmyProfile) -> None:
    """Pattern at a true sentence boundary (after period+space) must match."""
    page_text = (
        "Background context here, followed by a complete sentence. "
        "The term Combat Engineer means a soldier qualified in mobility, "
        "countermobility, and survivability operations on the battlefield."
    )
    doc = _mock_doc_from_pages([page_text])
    out = extract_inline_definitions(doc, army)
    terms = [e["term"] for e in out]
    assert "Combat Engineer" in terms, (
        f"After period+space, pattern must still match. Got: {terms}"
    )
