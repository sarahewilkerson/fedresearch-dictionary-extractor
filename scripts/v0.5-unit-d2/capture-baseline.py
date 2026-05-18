"""A3 — capture v0.5 baseline for the N range-validated D-2 docs.

For each doc in the verified cohort (range_correct=true in range-validation.csv),
run analyze_pdf and record the metadata + asserted entry_count=0.

Output: validation_set/v0.5-unit-d2-baseline.json.
"""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
COHORT_CSV = REPO_ROOT / "validation_set" / "v0.5-unit-d2-cohort.csv"
RANGE_CSV = REPO_ROOT / "validation_set" / "v0.5-unit-d2-range-validation.csv"
OUT_JSON = REPO_ROOT / "validation_set" / "v0.5-unit-d2-baseline.json"
PDF_DIR = Path("/tmp/v05-unit0/pdfs")


def _skip_comments(path: Path):
    text = path.read_text()
    return io.StringIO("\n".join(line for line in text.splitlines() if not line.startswith("#")))


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from fedresearch_dictionary_extractor.core.analyzer import analyze_pdf

    # Verified cohort = range_correct=true
    verified_ids = set()
    for r in csv.DictReader(_skip_comments(RANGE_CSV)):
        if r["range_correct"] == "true":
            verified_ids.add(r["document_id"])

    cohort = {r["document_id"]: r for r in csv.DictReader(_skip_comments(COHORT_CSV))}

    baseline = {"source_commit": "ed8ede5", "verified_cohort_size": len(verified_ids), "entries": []}
    for doc_id in sorted(verified_ids):
        r = cohort[doc_id]
        pdf_path = PDF_DIR / Path(r["gcs_key"]).name
        out = analyze_pdf(str(pdf_path), profile_name="army", deterministic=True)
        md = out["metadata"]
        gp = md.get("glossary_pages") or []
        baseline["entries"].append({
            "document_id": doc_id,
            "canonical_id": r["canonical_id"],
            "detected_range_0idx": [gp[0] - 1, gp[-1] - 1] if gp else None,
            "section_structure": md.get("section_structure"),
            "section_ii_pages_1idx": md.get("section_ii_pages"),
            "section_ii_narrowing_fired": md.get("section_ii_narrowing_fired"),
            "glossary_used_legacy_fallback": md.get("glossary_used_legacy_fallback"),
            "entry_count": len(out.get("entries", [])),
        })
        if baseline["entries"][-1]["entry_count"] != 0:
            raise SystemExit(
                f"baseline violation: {doc_id} has entry_count={baseline['entries'][-1]['entry_count']}, "
                f"expected 0 (verified cohort is parser-dead-end)"
            )

    OUT_JSON.write_text(json.dumps(baseline, indent=2) + "\n")
    print(f"baseline: {len(baseline['entries'])} entries, all entry_count=0", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
