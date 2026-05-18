"""A6 — scan for whether 1-page gap tolerance would change block selection.

For each PDF in the combined 27-cohort + 31-validation set:
1. Forward-scan for header-pattern matches.
2. Group into strict-contiguous blocks.
3. For each adjacent block pair (B1, B2) where B2.start == B1.end + 2 (i.e.,
   exactly one missing page between them with substantive text on that page):
   compute combined_size = len(B1) + len(B2) + 1.
   If combined_size > current_largest_block_size, this is a TOLERANCE-POSITIVE
   case: 1-page tolerance would change the chosen block.
4. Decision: if any TOLERANCE-POSITIVE case is found, use 1-page tolerance;
   else strict-contiguous.

This is a tighter heuristic than my iter-1 attempt which counted ALL gaps
between first and last match — that over-counted Class-3 scattered-body matches.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).parent.parent.parent
COHORT_CSV = REPO_ROOT / "validation_set" / "v0.5-unit0-cohort.csv"
COHORT_PDFS = Path("/tmp/v05-unit0/pdfs")
VAL_PDFS = REPO_ROOT / "validation_set" / "pdfs"
OUT = REPO_ROOT / "validation_set" / "v0.5-unit-d1-gap-scan.txt"

sys.path.insert(0, str(REPO_ROOT / "src"))
from fedresearch_dictionary_extractor.profiles import get_profile  # noqa: E402


def matching_pages(pdf_path: Path) -> tuple[list[int], dict[int, int]]:
    """Return (matching_pages, page_text_len_by_idx)."""
    profile = get_profile("army")
    header_res = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in profile.glossary_header_patterns]
    matches: list[int] = []
    text_lens: dict[int, int] = {}
    doc = fitz.open(str(pdf_path))
    try:
        for i in range(len(doc)):
            try:
                t = doc[i].get_text("text")
            except Exception:
                t = ""
            text_lens[i] = len(t.strip())
            if any(r.search(t) for r in header_res):
                matches.append(i)
        return matches, text_lens
    finally:
        doc.close()


def strict_blocks(matches: list[int]) -> list[list[int]]:
    if not matches:
        return []
    blocks: list[list[int]] = []
    cur = [matches[0]]
    for p in matches[1:]:
        if p == cur[-1] + 1:
            cur.append(p)
        else:
            blocks.append(cur)
            cur = [p]
    blocks.append(cur)
    return blocks


def tolerance_positive(pdf_path: Path) -> tuple[bool, list[tuple[int, int, int]]]:
    """Return (would_tolerance_change_choice, [(block1_size, block2_size, combined)] for relevant pairs)."""
    matches, text_lens = matching_pages(pdf_path)
    blocks = strict_blocks(matches)
    if len(blocks) < 2:
        return False, []
    current_largest = max(len(b) for b in blocks)
    findings: list[tuple[int, int, int]] = []
    for i in range(len(blocks) - 1):
        b1, b2 = blocks[i], blocks[i + 1]
        if b2[0] != b1[-1] + 2:
            continue  # not a 1-page gap
        gap_page = b1[-1] + 1
        # Only count if the gap page has substantive text (real extraction failure
        # of headers, not a blank intentional break)
        if text_lens.get(gap_page, 0) < 200:
            continue
        combined = len(b1) + len(b2) + 1
        # Refinement: only count as tolerance-positive if the merged block
        # is meaningfully large (≥5 pages). The 1+1=3 case is body-noise
        # merging — two isolated body references becoming a fake "block";
        # strict-contiguous correctly rejects those.
        if combined > current_largest and combined >= 5:
            findings.append((len(b1), len(b2), combined))
    return bool(findings), findings


def main() -> int:
    affected: list[tuple[str, Path, list[tuple[int, int, int]]]] = []

    cohort_rows = list(csv.DictReader(COHORT_CSV.open()))
    with (REPO_ROOT / "validation_set" / "v0.5-unit0-measurements.tsv").open() as f:
        measurements = list(csv.DictReader(f, delimiter="\t"))
    class23_ids = {r["document_id"] for r in measurements if r["range_match"] in ("overlap", "disjoint")}
    seen_pdfs: set[str] = set()
    for row in cohort_rows:
        if row["document_id"] not in class23_ids:
            continue
        pdf = COHORT_PDFS / Path(row["gcs_key"]).name
        if pdf.name in seen_pdfs or not pdf.exists():
            continue
        seen_pdfs.add(pdf.name)
        positive, findings = tolerance_positive(pdf)
        if positive:
            affected.append(("cohort", pdf, findings))

    for pdf in sorted(VAL_PDFS.glob("*.pdf")):
        positive, findings = tolerance_positive(pdf)
        if positive:
            affected.append(("validation", pdf, findings))

    decision = "STRICT_CONTIGUOUS" if not affected else "ONE_PAGE_TOLERANCE"

    OUT.write_text(
        "# v0.5 Unit D-1 gap-tolerance empirical scan (revised heuristic)\n"
        "# Heuristic: scan finds docs where 1-page-tolerance WOULD change the\n"
        "# chosen largest-block (i.e., merging two adjacent blocks across a\n"
        "# substantive-text gap page produces a larger block than the current\n"
        "# strict-mode winner). Class-3 scattered-body matches don't fire here\n"
        "# because their isolated matches don't form combinable adjacent blocks.\n\n"
        f"DECISION: {decision}\n"
        f"FINDINGS: {len(affected)} doc(s) where tolerance would change block selection\n\n"
        + ("(none — strict-contiguous safe across the 27+31 doc combined surface)\n" if not affected else
           "\n".join(
               f"{label}  {pdf.name}\n  block-pairs that would merge: " +
               ", ".join(f"({b1}+{b2}={comb})" for b1, b2, comb in findings)
               for label, pdf, findings in affected))
    )
    print(f"{decision}: {len(affected)} doc(s) where tolerance would change choice", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
