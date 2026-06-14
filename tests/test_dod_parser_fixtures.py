"""P2-B: DoD parser fixture test (PDF-free CI gate).

Loads a committed real-PDF capture (get_text("dict")) of DODI 3150.09's
glossary pages and asserts parse_glossary_entries(DOD) extracts the expected
terms with no structural-header / continuation false positives. Runs in CI
without the source PDF (the gitignored PDF is re-fetchable via the manifest).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock

from fedresearch_dictionary_extractor.extractors.glossary import parse_glossary_entries
from fedresearch_dictionary_extractor.profiles import get_profile

FIXTURE = Path(__file__).parent / "fixtures" / "glossary_parser_dod" / "DODI_3150.09.json"
DOD = get_profile("dod")


def _mock_doc(fixture: dict) -> MagicMock:
    total = fixture["total_pages"]
    page_data = {int(k): v for k, v in fixture["pages"].items()}
    page_mocks = []
    for i in range(total):
        page = MagicMock()
        if i in page_data:
            page.get_text.side_effect = lambda fmt="text", _i=i: (
                page_data[_i]["page_dict"] if fmt == "dict" else page_data[_i]["page_text"]
            )
        else:
            page.get_text.side_effect = lambda fmt="text": ({"blocks": []} if fmt == "dict" else "")
        page.rect = MagicMock()
        page.rect.height = page_data.get(i, {}).get("page_dict", {}).get("height", 792)
        page.get_label = MagicMock(return_value=None)
        page_mocks.append(page)
    doc = MagicMock()
    doc.__getitem__.side_effect = lambda i: page_mocks[i]
    doc.__len__.return_value = total
    return doc


def test_dodi_3150_09_parser_extracts_expected_terms() -> None:
    fixture = json.loads(FIXTURE.read_text())
    doc = _mock_doc(fixture)
    start, end = fixture["capture_range_0idx"]
    entries = parse_glossary_entries(doc, start, end, DOD)
    terms = [e["term"] for e in entries]

    # Real DoD glossary headwords must be present.
    for expected in ["BSA", "CBR hardness", "DODIN", "decontamination", "materiel developer"]:
        assert expected in terms, f"missing expected term {expected!r}"

    # Cross-ref pointer definitions are kept.
    bsa = next(e for e in entries if e["term"] == "BSA")
    assert "Reference (k)" in bsa["definition"]

    # No structural-header / section-marker false positives (not "partisan").
    header_fp = re.compile(r"^(PART\s+[IVXL0-9]|GLOSSARY|SECTION\b|ABBREVIATIONS\b)", re.I)
    for bad in terms:
        assert not header_fp.match(bad), f"header FP {bad!r}"

    # Recall floor on the captured set (>=0.85 of the committed expected set).
    expected_terms = set(fixture["expected_terms"])
    recall = len(expected_terms & set(terms)) / len(expected_terms)
    assert recall >= 0.85, f"recall {recall:.2f} below floor"
