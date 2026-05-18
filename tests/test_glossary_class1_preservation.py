"""v0.5 D-1: Class-1 range preservation regression.

Per the plan §H8: the 11 Class-1 docs (exact-range parser failures) must
have their detected range preserved EXACTLY across the v0.4 → v0.5 change.
D-2 will trace parser dead-ends from those exact pages; if D-1 shifts the
range, D-2's baseline is destroyed.

Reference data: validation_set/v0.5-unit-d1-class1-range-preservation.yaml
(captured at commit c4d1611 by scripts/v0.5-unit-d1/capture-class1-ranges.py).
"""
from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from fedresearch_dictionary_extractor.extractors.glossary import find_glossary_page_range
from fedresearch_dictionary_extractor.profiles import get_profile

REPO = Path(__file__).parent.parent
PDF_DIR = Path("/tmp/v05-unit0/pdfs")
COHORT_CSV = REPO / "validation_set" / "v0.5-unit0-cohort.csv"
PRESERVATION_YAML = REPO / "validation_set" / "v0.5-unit-d1-class1-range-preservation.yaml"


def _parse_yaml() -> list[dict]:
    """Minimal YAML parser sufficient for our flat-list schema (avoids PyYAML dep)."""
    entries: list[dict] = []
    cur: dict | None = None
    for line in PRESERVATION_YAML.read_text().splitlines():
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


def _gcs_keys() -> dict[str, str]:
    import csv
    keys = {}
    with COHORT_CSV.open() as f:
        for row in csv.DictReader(f):
            keys[row["document_id"]] = row["gcs_key"]
    return keys


CLASS1_ENTRIES = _parse_yaml()
GCS_KEYS = _gcs_keys()
ARMY = get_profile("army")


@pytest.mark.parametrize("entry", CLASS1_ENTRIES, ids=lambda e: e["document_id"][:16])
def test_class1_ranges_preserved_under_v05(entry: dict) -> None:
    """For each Class-1 doc, the v0.5 detected range MUST match v0.4's."""
    doc_id = entry["document_id"]
    expected_start = int(entry["expected_start"])
    expected_end = int(entry["expected_end"])
    gcs_key = GCS_KEYS[doc_id]
    pdf_path = PDF_DIR / Path(gcs_key).name
    if not pdf_path.exists():
        pytest.skip(f"PDF not locally available: {pdf_path}")
    doc = fitz.open(str(pdf_path))
    try:
        result = find_glossary_page_range(doc, ARMY)
    finally:
        doc.close()
    assert result is not None, f"v0.5 returned None for Class-1 doc {doc_id} (regression vs v0.4)"
    start, end = result
    assert (start, end) == (expected_start, expected_end), (
        f"Class-1 range drift for {doc_id}: v0.4=({expected_start},{expected_end}), "
        f"v0.5=({start},{end}). D-2's parser-trace baseline depends on these pages."
    )
