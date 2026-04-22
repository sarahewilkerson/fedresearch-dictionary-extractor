"""
Tests for normalize_term — also runs against the shared YAML fixture.
The same fixture is consumed by the FedResearch backend's TypeScript
implementation; both must agree on every case.
"""
from pathlib import Path

import pytest
import yaml

from fedresearch_dictionary_extractor.normalize import normalize_term

FIXTURE = Path(__file__).parent / "fixtures" / "normalization_cases.yaml"


def _load_cases():
    data = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    return [(c["input"], c["normalized"]) for c in data["cases"]]


@pytest.mark.parametrize(("raw", "expected"), _load_cases())
def test_normalization_fixture(raw: str, expected: str) -> None:
    """Every shared fixture case must produce its expected normalized form."""
    assert normalize_term(raw) == expected


def test_idempotent() -> None:
    """normalize(normalize(x)) == normalize(x)."""
    sample_inputs = ["Combatant Command", "U.C.M.J.", "  spaced  ", "“Smart” quotes"]
    for s in sample_inputs:
        once = normalize_term(s)
        twice = normalize_term(once)
        assert once == twice, f"Not idempotent on {s!r}: {once!r} → {twice!r}"


def test_handles_none_like_inputs() -> None:
    assert normalize_term("") == ""


def test_does_not_alter_lowercase_with_internal_dots() -> None:
    """e.g., should be preserved (lowercase context)."""
    assert "e.g." in normalize_term("e.g., something")
