"""v0.5 D-1: Class-2 + Class-3 acceptance tests.

Parametrized over the 27 doc IDs in validation_set/v0.5-unit-d1-acceptance.yaml.
Each entry has an `expected_v05_range`, `acceptance_relation` (default 'exact'),
and `disposition` ('active' | 'deferred_to_d2' | 'scope_decision' |
'known_failure_with_followup_unit').

Two test suites:
1. test_class2_class3_ranges_exact — parametrized; per-doc range-correctness
2. test_acceptance_misses_are_categorized — meta-test: every miss must have
   a `disposition` field set (no anonymous failures).
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import fitz
import pytest

from fedresearch_dictionary_extractor.extractors.glossary import find_glossary_page_range
from fedresearch_dictionary_extractor.profiles import get_profile

REPO = Path(__file__).parent.parent
PDF_DIR = Path("/tmp/v05-unit0/pdfs")
COHORT_CSV = REPO / "validation_set" / "v0.5-unit0-cohort.csv"
ACCEPTANCE_YAML = REPO / "validation_set" / "v0.5-unit-d1-acceptance.yaml"


def _parse_acceptance_yaml() -> list[dict]:
    """Minimal YAML parser for our flat-list schema."""
    entries: list[dict] = []
    cur: dict | None = None
    for line in ACCEPTANCE_YAML.read_text().splitlines():
        if line.startswith("  - "):
            if cur is not None:
                entries.append(cur)
            cur = {}
            key, _, val = line[4:].partition(":")
            cur[key.strip()] = val.strip()
        elif line.startswith("    ") and cur is not None:
            key, _, val = line.strip().partition(":")
            cur[key.strip()] = val.strip()
    if cur is not None:
        entries.append(cur)
    return entries


def _parse_range_field(s: str) -> list[int] | None:
    """Parse '[a, b]' or 'None' to list[int] or None."""
    s = s.strip()
    if s == "None":
        return None
    m = re.match(r"\[(\d+),\s*(\d+)\]", s)
    if not m:
        return None
    return [int(m.group(1)), int(m.group(2))]


ENTRIES = _parse_acceptance_yaml()
ACTIVE_ENTRIES = [e for e in ENTRIES if e.get("disposition", "active") == "active"]

GCS_KEYS: dict[str, str] = {}
with COHORT_CSV.open() as f:
    for row in csv.DictReader(f):
        GCS_KEYS[row["document_id"]] = row["gcs_key"]

ARMY = get_profile("army")


@pytest.mark.parametrize(
    "entry",
    ACTIVE_ENTRIES,
    ids=lambda e: e["document_id"][:16],
)
def test_class2_class3_ranges_active_docs_match_expected(entry: dict) -> None:
    """For each active-disposition Class-2/3 doc, v0.5 must produce the
    expected_v05_range exactly (or honor the documented acceptance_relation)."""
    doc_id = entry["document_id"]
    expected = _parse_range_field(entry["expected_v05_range"])
    relation = entry.get("acceptance_relation", "exact")
    if expected is None:
        pytest.skip(f"{doc_id}: no expected_v05_range in YAML")
    pdf_path = PDF_DIR / Path(GCS_KEYS[doc_id]).name
    if not pdf_path.exists():
        pytest.skip(f"PDF not locally available: {pdf_path}")
    doc = fitz.open(str(pdf_path))
    try:
        result = find_glossary_page_range(doc, ARMY)
    finally:
        doc.close()
    assert result is not None, f"v0.5 returned None for {doc_id}"
    start, end = result

    if relation == "exact":
        assert [start, end] == expected, (
            f"{doc_id}: expected v0.5 range {expected}, got [{start}, {end}]. "
            f"old_v04={entry.get('old_v04_range')}, loose={entry.get('loose_heuristic_range')}"
        )
    else:
        # Non-exact relation; minimum required is the rationale documented.
        # Defer interpretation to per-doc plan inspection.
        pytest.fail(
            f"{doc_id}: acceptance_relation={relation!r} requires plan-side "
            f"interpretation — not implemented in this generic test"
        )


def test_acceptance_misses_are_categorized() -> None:
    """Meta-test: every Class-2+3 entry has a disposition field set.
    No anonymous failures. (Plan §H7, Codex iter-2 #3.)"""
    valid_dispositions = {
        "active",
        "deferred_to_d2",
        "scope_decision",
        "known_failure_with_followup_unit",
    }
    bad_entries = []
    for e in ENTRIES:
        d = e.get("disposition", "")
        if d not in valid_dispositions:
            bad_entries.append((e["document_id"], d))
    assert not bad_entries, (
        f"{len(bad_entries)} entries have invalid/missing disposition: {bad_entries}. "
        f"Every Class-2/3 doc must be categorized."
    )


def test_active_entry_count_meets_acceptance_floor() -> None:
    """Plan acceptance: ≥24 of 27 docs have disposition='active' with
    acceptance_relation='exact'. The remaining ≤3 may have documented
    deferral, but the meta-acceptance floor of 24 active+exact must hold."""
    active_exact = [
        e for e in ENTRIES
        if e.get("disposition", "active") == "active"
        and e.get("acceptance_relation", "exact") == "exact"
    ]
    assert len(active_exact) >= 24, (
        f"Only {len(active_exact)} active+exact entries; plan requires ≥24. "
        f"Either tighten the acceptance YAML or document the deferrals."
    )
