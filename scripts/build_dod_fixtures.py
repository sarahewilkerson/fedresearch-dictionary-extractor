"""Regenerate the committed DoD parser fixtures from local PDFs.

Deterministic: given the manifest PDFs (fetch_dod_corpus.py), rebuilds
tests/fixtures/glossary_parser_dod/<name>.json (captured get_text("dict") of
the detected glossary pages + the parsed expected_terms). Commit the result.

    python scripts/build_dod_fixtures.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import fitz

from fedresearch_dictionary_extractor.extractors.glossary import (
    find_glossary_page_range,
    parse_glossary_entries,
)
from fedresearch_dictionary_extractor.profiles import get_profile

REPO = Path(__file__).parent.parent
PDF_DIR = REPO / "validation_set" / "dod_pdfs"
FIXTURE_DIR = REPO / "tests" / "fixtures" / "glossary_parser_dod"
DOD = get_profile("dod")

# (fixture name, pdf filename, family) — the committed PDF-free parser fixtures.
TARGETS = [("DODI_3150.09", "DODI_3150.09.pdf", "DoDI")]


def main() -> int:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name, pdf_name, family in TARGETS:
        pdf = PDF_DIR / pdf_name
        if not pdf.exists():
            print(f"missing {pdf} (run fetch_dod_corpus.py)", file=sys.stderr)
            return 1
        doc = fitz.open(str(pdf))
        rng = find_glossary_page_range(doc, DOD)
        if rng is None:
            print(f"no glossary range for {pdf_name}", file=sys.stderr)
            return 1
        start, end = rng
        pages = {
            str(i): {
                "page_dict": doc[i].get_text("dict"),
                "page_text": doc[i].get_text("text"),
            }
            for i in range(start, end + 1)
        }
        entries = parse_glossary_entries(doc, start, end, DOD)
        fixture = {
            "source": f"{pdf_name} (prod gs://fr-docs-prod), captured P2-B",
            "family": family,
            "total_pages": len(doc),
            "detected_range_0idx": [start, end],
            "capture_range_0idx": [start, end],
            "expected_terms": [e["term"] for e in entries],
            "pages": pages,
        }
        out = FIXTURE_DIR / f"{name}.json"
        out.write_text(json.dumps(fixture))
        print(f"wrote {out} (range {rng}, {len(entries)} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
