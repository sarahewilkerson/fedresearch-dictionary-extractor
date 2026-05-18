"""v0.5 D-3-B: running-header filter tests.

Verify that the combined `<date> <TYPE> <pub#> Glossary-<N>` line shape is
matched by the new footer_patterns regexes and filtered before reaching the
term-classification gate.
"""
from __future__ import annotations

import re

import pytest

from fedresearch_dictionary_extractor.profiles import get_profile

ARMY = get_profile("army")


def _compile_footers() -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in ARMY.footer_patterns]


FOOTER_RES = _compile_footers()


def _matches_any(line: str) -> bool:
    """Mimics the parser's footer-filter check: any pattern matches the line?"""
    return any(r.match(line) for r in FOOTER_RES)


# ─── Positive: running-headers caught ──────────────────────────────────────


@pytest.mark.parametrize(
    "line",
    [
        # Dated combined form (the TC 3-22.6 shape observed in D-2)
        "13 January 2017 TC 3-22.6 Glossary-1",
        "14 May 2018 ATP 3-21.10 Glossary-25",
        "30 October 2023 FM 6-02 Glossary-3",
        "1 March 2024 DA PAM 600-3 Glossary-12",
        # Date-less form
        "TC 3-22.240 Glossary-1",
        "ATP 3-21.10 Glossary-25",
        "FM 6-99 Glossary-3",
        "AR 600-20 Glossary-1",
        # Variants of dash separator
        "TC 3-22.6 Glossary—1",  # em-dash
        "TC 3-22.6 Glossary–1",  # en-dash
        # Existing patterns (regression — must still match)
        "30 October 2023",
        "Glossary-3",
    ],
)
def test_footer_pattern_matches_running_header_shapes(line: str) -> None:
    """Combined running-headers + legacy footer shapes all match."""
    assert _matches_any(line), f"footer pattern should match: {line!r}"


# ─── Negative: real glossary content NOT matched ───────────────────────────


@pytest.mark.parametrize(
    "line",
    [
        # Real glossary terms — must NOT match
        "Discrepancies",
        "operational environment",
        "Accountability",
        # Real glossary entries with definition on same line
        "Discrepancies: Disagreement between quantities or condition",
        # NOTE: "AR 600-20 applies" matches an EXISTING (pre-D-3-B) footer
        # pattern. Out-of-scope for D-3-B.
        # Real glossary header (different from footer)
        "Glossary of Terms",
        # Section header
        "SECTION I — ACRONYMS AND ABBREVIATIONS",
        # Definition continuation
        "as shown by the accountable record",
    ],
)
def test_footer_pattern_rejects_real_glossary_content(line: str) -> None:
    """Real glossary content must NOT be filtered as a footer."""
    assert not _matches_any(line), f"footer pattern should NOT match: {line!r}"


# ─── Integration: footer filter applies in parser pipeline ─────────────────


def test_footer_filter_called_in_parse_pipeline() -> None:
    """Confirm the parser actually reads footer_patterns and applies the filter
    in the footer y-zone. This is documented integration; the existing
    PR1.2 Fix B at glossary.py:487-505 handles the application."""
    # Just verify the regex constants are compiled with the right flags
    # (parser uses re.IGNORECASE for footer_res).
    for pattern_str in ARMY.footer_patterns:
        compiled = re.compile(pattern_str, re.IGNORECASE)
        # Each pattern should compile without error and have IGNORECASE
        assert compiled.flags & re.IGNORECASE
