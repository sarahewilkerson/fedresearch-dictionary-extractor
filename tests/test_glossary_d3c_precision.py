"""v0.5 D-3-C: parser precision tightening tests.

1. _validate_term rejects lowercase short stopwords.
2. Analyzer-level fallback re-parses over full range when narrowing
   produces 0 entries.
"""
from __future__ import annotations

import re

from fedresearch_dictionary_extractor.extractors.glossary import _validate_term
from fedresearch_dictionary_extractor.profiles import get_profile

ARMY = get_profile("army")
INVALID_RES = [re.compile(p, re.IGNORECASE) for p in ARMY.invalid_term_patterns]


def test_lowercase_stopword_rejected() -> None:
    """`the` is a classification slip, not a glossary term."""
    assert _validate_term("the", None, INVALID_RES) is False


def test_lowercase_stopwords_rejected_parametrized() -> None:
    for word in ["the", "there", "this", "that", "when", "with"]:
        assert _validate_term(word, None, INVALID_RES) is False, f"{word!r} should be rejected"


def test_capitalized_short_word_still_admitted() -> None:
    """Real glossary headwords starting with a capital are preserved."""
    assert _validate_term("There", None, INVALID_RES) is True


def test_acronym_shaped_short_word_admitted() -> None:
    """ALL-CAPS short acronyms must still pass (not classified as stopwords)."""
    assert _validate_term("THE", None, INVALID_RES) is True  # all-caps treated as acronym
    assert _validate_term("AO", None, INVALID_RES) is True
    assert _validate_term("DOD", None, INVALID_RES) is True


def test_long_lowercase_word_admitted() -> None:
    """Long lowercase words are valid glossary terms (e.g., 'countermobility')."""
    assert _validate_term("countermobility", None, INVALID_RES) is True
    assert _validate_term("synchronization", None, INVALID_RES) is True
