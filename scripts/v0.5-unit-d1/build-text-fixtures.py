"""A7 — build realistic-PDF text fixtures for the 3 representative docs.

For each fixture target, extract `page.get_text("text")` for the relevant
glossary range + ±10 pages of context. Emit JSON `{page_idx_0based: text}`.

Fixture targets:
- atp-3-21-10: Class 2 prototype — running-header footers, real glossary 580-604
- ar-12-15: Class 3 prototype — v0.4 picked body ref at page 343, real at page 21
- ar-11-7: front-matter-heavy validation case (regression sentinel)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).parent.parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "glossary_range_v05"
FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

TARGETS = [
    ("atp-3-21-10",
     "/tmp/v05-unit0/pdfs/ATP 3-21.10 INFANTRY RIFLE COMPANY 2018_05_14_OCR.pdf",
     570, 615),  # range 580-604 + 10 each side
    ("ar-12-15",
     "/tmp/v05-unit0/pdfs/AR 12-15 JOINT SECURITY COOPERATION EDUCATION AND TRAINING {SECNAVINST 4950.4B; AFI 16-105} ASA_AL_T 2011_01_03_OCR.pdf",
     0, 60),  # cover-to-page-60 (TOC + early glossary + body ref reach)
    ("ar-11-7",
     str(REPO_ROOT / "validation_set" / "pdfs" / "AR_11-7_INTERNAL_REVIEW_PROGRAM_ASA_FM_C_2025_05_21_OCR.pdf"),
     0, 50),  # front-matter focus
]


def main() -> int:
    for name, pdf_path, start, end in TARGETS:
        path = Path(pdf_path)
        if not path.exists():
            print(f"missing: {pdf_path}", file=sys.stderr)
            continue
        doc = fitz.open(str(path))
        try:
            pages: dict[str, str] = {}
            actual_end = min(end, len(doc) - 1)
            for i in range(start, actual_end + 1):
                try:
                    pages[str(i)] = doc[i].get_text("text")
                except Exception as exc:
                    pages[str(i)] = f""  # empty; preserves page slot
            payload = {
                "source_pdf": path.name,
                "page_range_inclusive_0based": [start, actual_end],
                "total_pages_in_pdf": len(doc),
                "pages": pages,
            }
            out = FIXTURE_DIR / f"{name}.json"
            out.write_text(json.dumps(payload, indent=2) + "\n")
            print(f"wrote {out.name} ({len(pages)} pages)", file=sys.stderr)
        finally:
            doc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
