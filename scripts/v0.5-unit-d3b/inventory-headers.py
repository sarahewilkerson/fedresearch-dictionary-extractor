"""D-3-B Step 1: inventory top-zone "Glossary" lines across 7+31 docs.

For each doc, extract every line in the top-150pt y-zone (HEADER_ZONE_Y)
that contains "Glossary" (case-insensitive). Classify each as running-header
vs real-glossary-content via simple heuristic + commit for reviewer
confirmation pre-implementation.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
TRACE_DIR = REPO_ROOT / "validation_set" / "v0.5-unit-d2-trace-summaries"
RANGE_CSV = REPO_ROOT / "validation_set" / "v0.5-unit-d2-range-validation.csv"
COHORT_CSV = REPO_ROOT / "validation_set" / "v0.5-unit-d2-cohort.csv"
PDF_DIR_COHORT = Path("/tmp/v05-unit0/pdfs")
PDF_DIR_VAL = REPO_ROOT / "validation_set" / "pdfs"
OUT_CSV = REPO_ROOT / "validation_set" / "v0.5-unit-d3b-running-header-inventory.csv"
HEADER_ZONE_Y = 150

# Proposed D-3-B patterns
PROPOSED_PATTERNS = [
    re.compile(r"^\s*(AR|FM|ADP|ATP|TC|PAM|TM|DA\s*PAM)\s+[\d\.\-–]+\s+Glossary[\s\-–—]+\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\s+(AR|FM|ADP|ATP|TC|PAM|TM|DA\s*PAM)\s+[\d\.\-–]+\s+Glossary[\s\-–—]+\d+\s*$", re.IGNORECASE),
]


def _skip_comments(path: Path):
    text = path.read_text()
    return io.StringIO("\n".join(line for line in text.splitlines() if not line.startswith("#")))


def extract_top_zone_glossary_lines(pdf_path: Path, glossary_pages: list[int]) -> list[dict]:
    """For each glossary page, return top-zone lines containing 'glossary'."""
    import fitz
    out = []
    doc = fitz.open(str(pdf_path))
    try:
        for page_idx in glossary_pages:
            if page_idx >= len(doc):
                continue
            page_dict = doc[page_idx].get_text("dict")
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue
                    y_pos = spans[0]["bbox"][1]
                    line_text = " ".join(s.get("text", "").strip() for s in spans).strip()
                    if y_pos < HEADER_ZONE_Y and "glossary" in line_text.lower():
                        matched_pattern = next(
                            (i for i, p in enumerate(PROPOSED_PATTERNS) if p.search(line_text)),
                            None,
                        )
                        out.append({
                            "page_idx": page_idx,
                            "y_pos": round(y_pos, 1),
                            "line_text": line_text[:120],
                            "matched_proposed_pattern": matched_pattern,
                        })
    finally:
        doc.close()
    return out


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from fedresearch_dictionary_extractor.core.analyzer import analyze_pdf

    rows: list[dict] = []

    # 1. P-2/hybrid docs from D-2 cohort (7 docs — those whose trace shows
    #    flush_summary.emitted=0 AND validate.passed > 0; the running-header
    #    was accepted as term)
    cohort_meta = {r["document_id"]: r for r in csv.DictReader(_skip_comments(COHORT_CSV))}
    verified = [r["document_id"] for r in csv.DictReader(_skip_comments(RANGE_CSV)) if r["range_correct"] == "true"]
    p2_candidates: list[str] = []
    for doc_id in verified:
        trace = TRACE_DIR / f"{doc_id}.json"
        if not trace.exists():
            continue
        s = json.loads(trace.read_text())
        # P-2 or hybrid: validate.passed > 0 (a term WAS accepted) AND flush.emitted == 0
        if s["validate_summary"]["passed"] > 0 and s["flush_summary"]["emitted"] == 0:
            p2_candidates.append(doc_id)
    print(f"P-2/hybrid candidates from D-2 trace: {len(p2_candidates)}", file=sys.stderr)

    for doc_id in p2_candidates:
        meta = cohort_meta[doc_id]
        pdf = PDF_DIR_COHORT / Path(meta["gcs_key"]).name
        if not pdf.exists():
            continue
        # Get glossary pages from baseline
        out_md = analyze_pdf(str(pdf), profile_name="army", deterministic=True)["metadata"]
        gp_1idx = out_md.get("glossary_pages") or []
        gp_0idx = [p - 1 for p in gp_1idx]
        for entry in extract_top_zone_glossary_lines(pdf, gp_0idx):
            entry["document_id"] = doc_id
            entry["source"] = "target_cohort"
            entry["canonical_id"] = meta["canonical_id"]
            rows.append(entry)

    # 2. 31-doc validation set
    for pdf in sorted(PDF_DIR_VAL.glob("*.pdf")):
        out = analyze_pdf(str(pdf), profile_name="army", deterministic=True)
        gp_1idx = out["metadata"].get("glossary_pages") or []
        gp_0idx = [p - 1 for p in gp_1idx]
        for entry in extract_top_zone_glossary_lines(pdf, gp_0idx):
            entry["document_id"] = pdf.stem
            entry["source"] = "validation_set"
            entry["canonical_id"] = pdf.stem
            rows.append(entry)

    # Add is_running_header heuristic: matches one of the proposed patterns
    for r in rows:
        r["is_running_header_heuristic"] = r["matched_proposed_pattern"] is not None
        r["needs_review"] = "yes" if r["matched_proposed_pattern"] is None else "no"

    OUT_CSV.write_text(
        "# v0.5 Unit D-3-B running-header inventory.\n"
        "# Top-zone (y<150) lines containing 'Glossary' across 7 target + 31 validation docs.\n"
        "# matched_proposed_pattern: index of the regex pattern that matched (None if no match — line needs reviewer classification).\n"
        "# needs_review: 'yes' if no proposed pattern matched (potential gap in patterns).\n\n"
    )
    if rows:
        with OUT_CSV.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["document_id", "canonical_id", "source", "page_idx", "y_pos", "line_text", "matched_proposed_pattern", "is_running_header_heuristic", "needs_review"])
            w.writeheader()
            for r in rows:
                w.writerow(r)

    matched = sum(1 for r in rows if r["matched_proposed_pattern"] is not None)
    needs_review = sum(1 for r in rows if r["matched_proposed_pattern"] is None)
    print(f"inventory: {len(rows)} top-zone Glossary lines; {matched} matched proposed patterns; {needs_review} need review", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
