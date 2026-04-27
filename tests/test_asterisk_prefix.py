"""Tests for asterisk-prefix term handling (PR-A v0.3.0 fix #2).

Army publications use leading ``*`` (single) and ``**`` (double) on glossary
terms to mark "changed since previous publication." The extractor must strip
these markers before the term hits classification and emission, AND record the
fact via ``flags=["changed_since_prior_pub"]`` so downstream consumers can
surface provenance without re-parsing the original PDF.

Without the strip, ``*field`` becomes a distinct term from ``field`` — see
FM 3-34 in tests/test_batch1_reconciled.py and validation_set/batch1_reconciled.yaml.
"""
from __future__ import annotations

import pytest

from fedresearch_dictionary_extractor.extractors.glossary import (
    _strip_asterisk_prefix,
    _flush,
)


CHANGED_FLAG = "changed_since_prior_pub"


# ----------------------------------------------------------------------
# _strip_asterisk_prefix helper
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected_term", "expected_stripped"),
    [
        ("field", "field", False),                       # no marker
        ("*field", "field", True),                       # single
        ("**engineer", "engineer", True),                # double
        ("***triple", "triple", True),                   # triple (defensive)
        ("* spaced", "spaced", True),                    # marker + leading space after
        ("*  double-space", "double-space", True),       # marker + multiple spaces
        ("plain term", "plain term", False),             # multi-word, no marker
        ("*multi word term", "multi word term", True),   # marker + multi-word
        ("re*generation", "re*generation", False),       # internal * preserved
        ("term*", "term*", False),                       # trailing-only * preserved
        ("*", "*", False),                               # bare * (degenerate; let validator reject)
        ("**", "**", False),                             # bare ** (degenerate)
        ("", "", False),                                 # empty
    ],
)
def test_strip_asterisk_prefix(raw: str, expected_term: str, expected_stripped: bool) -> None:
    out_term, was_stripped = _strip_asterisk_prefix(raw)
    assert out_term == expected_term
    assert was_stripped is expected_stripped


# ----------------------------------------------------------------------
# _flush propagates flags onto the emitted entry
# ----------------------------------------------------------------------


class _FakeDoc:
    """Minimal fitz.Document shim — _flush only calls _safe_page_label which
    calls doc[idx].get_label(); return None to skip the label path."""

    class _Page:
        def get_label(self) -> str | None:
            return None

    def __getitem__(self, _idx: int):
        return self._Page()


class _FakeProfile:
    """Minimal ReferenceProfile shim — _flush only reads citation utilities,
    not profile attributes."""


def test_flush_propagates_flag_when_provided() -> None:
    """_flush must emit the entry with the flags arg appended, not [] default."""
    entries: list[dict] = []
    _flush(
        entries,
        current_term="field",
        current_def_lines=["force engineering The application of Army engineering"],
        page_idx=10,
        profile=_FakeProfile(),
        doc=_FakeDoc(),
        citation_pattern=r"\(AR \d",
        confidence=0.95,
        source_type="glossary",
        flags=[CHANGED_FLAG],
    )
    assert len(entries) == 1
    assert entries[0]["term"] == "field"
    assert entries[0]["flags"] == [CHANGED_FLAG]


def test_flush_default_flags_unchanged_when_not_provided() -> None:
    """Back-compat: omitting the flags arg yields the legacy empty list."""
    entries: list[dict] = []
    _flush(
        entries,
        current_term="ordinary",
        current_def_lines=["A perfectly normal definition."],
        page_idx=5,
        profile=_FakeProfile(),
        doc=_FakeDoc(),
        citation_pattern=r"\(AR \d",
        confidence=0.95,
        source_type="glossary",
    )
    assert len(entries) == 1
    assert entries[0]["flags"] == []


def test_flush_does_not_share_flag_list_across_entries() -> None:
    """Defensive: _flush must not let mutable-default-style aliasing leak
    flags from one call into the next entry's list."""
    entries: list[dict] = []
    flags_a = [CHANGED_FLAG]
    _flush(
        entries,
        current_term="alpha",
        current_def_lines=["First definition."],
        page_idx=1,
        profile=_FakeProfile(),
        doc=_FakeDoc(),
        citation_pattern=r"\(AR \d",
        confidence=0.95,
        source_type="glossary",
        flags=flags_a,
    )
    _flush(
        entries,
        current_term="beta",
        current_def_lines=["Second definition."],
        page_idx=1,
        profile=_FakeProfile(),
        doc=_FakeDoc(),
        citation_pattern=r"\(AR \d",
        confidence=0.95,
        source_type="glossary",
    )
    assert entries[0]["flags"] == [CHANGED_FLAG]
    assert entries[1]["flags"] == []
    # Mutating the input list after the call must not affect the entry.
    flags_a.append("mutated_after_flush")
    assert entries[0]["flags"] == [CHANGED_FLAG]
