r"""Unit tests for ArmyProfile.invalid_term_patterns — v0.2.a additions.

Covers the new `^(AR|FM|ADP|ATP|TC|PAM|TM|DA\s*PAM)\s+\d+\s*$` pattern
(pre-hyphen citation fragment) + negative-space proofs that common
legitimate terms still pass.

Tests N1-N15 per docs/plans/2026-04-24-invalid-term-blocklist.md §6.
"""
from __future__ import annotations

import re

import pytest

from fedresearch_dictionary_extractor.extractors.glossary import _validate_term
from fedresearch_dictionary_extractor.profiles.army import ArmyProfile


@pytest.fixture(scope="module")
def invalid_res() -> list[re.Pattern]:
    profile = ArmyProfile()
    return [re.compile(p, re.IGNORECASE) for p in profile.invalid_term_patterns]


# ── N1-N2: specific target terms ──────────────────────────────────────────

def test_n1_ar_124_rejected(invalid_res: list[re.Pattern]) -> None:
    """N1: 'AR 124' matches new pre-hyphen fragment pattern."""
    assert _validate_term("AR 124", None, invalid_res) is False


def test_n2_ar_140_rejected(invalid_res: list[re.Pattern]) -> None:
    """N2: 'AR 140' matches new pre-hyphen fragment pattern."""
    assert _validate_term("AR 140", None, invalid_res) is False


# ── N3-N10: per-family rejection (parametrized) ───────────────────────────

@pytest.mark.parametrize(
    "term",
    [
        "AR 123",
        "FM 6",
        "ADP 7",
        "ATP 12",
        "TC 3",
        "PAM 350",
        "TM 1001",
        "DA PAM 600",
        "DA  PAM 190",   # multi-space variant — regex allows \s*
        "ar 124",        # case-insensitive via re.IGNORECASE
        "fm 6",
    ],
)
def test_n3_to_n10_per_family_rejection(
    term: str, invalid_res: list[re.Pattern]
) -> None:
    """Every <TYPE> <digits> without hyphen rejected (structural invariant:
    Army doctrine always uses <TYPE> <series>-<publication>)."""
    assert _validate_term(term, None, invalid_res) is False


# ── N11: existing hyphenated-citation pattern still fires ─────────────────

def test_n11_existing_hyphenated_citation_still_rejected(
    invalid_res: list[re.Pattern],
) -> None:
    """Regression guard: 'AR 124-210' rejected by existing pattern (unchanged)."""
    assert _validate_term("AR 124-210", None, invalid_res) is False


# ── N12-N15: negative-space — legitimate terms must still validate ───────

@pytest.mark.parametrize(
    "term",
    [
        "Equipment concentration site",     # N12: real glossary term, near-miss
        "Equip",                            # N13: bare word, short but real
        "AR",                               # N14: bare publication type, no digits
        "AR 124-210 Supplement",            # N15: hyphenated + suffix, not just citation
    ],
)
def test_n12_to_n15_negative_space(
    term: str, invalid_res: list[re.Pattern]
) -> None:
    """The new pattern must not over-match legitimate terms."""
    assert _validate_term(term, None, invalid_res) is True
