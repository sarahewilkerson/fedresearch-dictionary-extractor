"""A4 — capture v0.4 full output for every PDF in validation_set/pdfs/.

Emits JSON with {detected_range, entries[], extractor_version, source_commit}
per doc. Used by tests/test_validation_set_golden.py to detect any unintended
behavior change introduced by D-1's find_glossary_page_range rewrite.

Must run with glossary.py unchanged from c4d1611 (asserted at start).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
PDF_DIR = REPO_ROOT / "validation_set" / "pdfs"
OUT_JSON = REPO_ROOT / "validation_set" / "v0.5-unit-d1-v04-golden-output.json"
EXPECTED_V04_COMMIT = "c4d1611a98b8ec76c68b7faf02b4cd3e47b77511"


def assert_glossary_unchanged() -> str:
    glossary_path = "src/fedresearch_dictionary_extractor/extractors/glossary.py"
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True
    ).stdout.strip()
    diff = subprocess.run(
        ["git", "diff", EXPECTED_V04_COMMIT, "--", glossary_path],
        cwd=REPO_ROOT, capture_output=True, text=True,
    ).stdout
    if diff.strip():
        raise SystemExit(
            f"glossary.py has been modified since c4d1611. Cannot capture v0.4 baseline."
        )
    return head_sha


def main() -> int:
    head_sha = assert_glossary_unchanged()
    print(f"capturing v0.4 golden output at HEAD={head_sha[:12]}", file=sys.stderr)

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from fedresearch_dictionary_extractor.core.analyzer import analyze_pdf

    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    print(f"found {len(pdfs)} PDFs", file=sys.stderr)

    golden: dict[str, dict] = {}
    for i, pdf in enumerate(pdfs, 1):
        print(f"  [{i}/{len(pdfs)}] {pdf.stem[:70]}", file=sys.stderr)
        try:
            out = analyze_pdf(str(pdf), profile_name="army", deterministic=True)
        except Exception as exc:
            golden[pdf.stem] = {
                "error": f"{type(exc).__name__}: {exc}",
                "source_commit": EXPECTED_V04_COMMIT,
            }
            continue
        md = out["metadata"]
        # detected_range from metadata (1-based glossary_pages list)
        gp = md.get("glossary_pages") or []
        detected_range = [gp[0] - 1, gp[-1] - 1] if gp else None  # convert to 0-based
        # term set (term_normalized) — stable identity for diff detection
        term_set = sorted({e["term_normalized"] for e in out.get("entries", []) if e.get("term_normalized")})
        golden[pdf.stem] = {
            "detected_range": detected_range,
            "term_count": len(out.get("entries", [])),
            "term_set": term_set,
            "section_structure": md.get("section_structure"),
            "section_ii_pages": md.get("section_ii_pages"),
            "section_ii_narrowing_fired": md.get("section_ii_narrowing_fired"),
            "glossary_used_legacy_fallback": md.get("glossary_used_legacy_fallback"),
            "extractor_version": out.get("extractor_version"),
            "source_commit": EXPECTED_V04_COMMIT,
        }

    OUT_JSON.write_text(json.dumps(golden, indent=2, sort_keys=True) + "\n")
    print(f"\nWrote {OUT_JSON} ({len(golden)} entries)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
