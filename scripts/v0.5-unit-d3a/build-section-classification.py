"""D-3-A S0: classify 11 D-2 cohort docs by Section II narrowing state.

Uses the D-2 trace summaries (already committed to main) — no PDF re-parse.
"""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
TRACE_DIR = REPO_ROOT / "validation_set" / "v0.5-unit-d2-trace-summaries"
RANGE_CSV = REPO_ROOT / "validation_set" / "v0.5-unit-d2-range-validation.csv"
OUT_CSV = REPO_ROOT / "validation_set" / "v0.5-unit-d3a-section-classification.csv"


def _skip_comments(path: Path):
    text = path.read_text()
    return io.StringIO("\n".join(line for line in text.splitlines() if not line.startswith("#")))


def main() -> int:
    # Verified cohort = range_correct=true (11 docs)
    verified_ids = []
    for r in csv.DictReader(_skip_comments(RANGE_CSV)):
        if r["range_correct"] == "true":
            verified_ids.append(r["document_id"])

    rows = []
    for doc_id in sorted(verified_ids):
        trace_file = TRACE_DIR / f"{doc_id}.json"
        if not trace_file.exists():
            rows.append({"document_id": doc_id, "target_group": "missing_trace"})
            continue
        s = json.loads(trace_file.read_text())
        md = s["metadata"]
        narrowing_fired = md.get("section_ii_narrowing_fired")
        section_structure = md.get("section_structure")
        if narrowing_fired:
            group = "B_narrowed_partial_benefit"
            rationale = "Section II narrowing clipped Section I; D-3-A helps only on Section II acronyms"
        else:
            group = "A_full_range_direct_target"
            rationale = "No narrowing; D-3-A directly admits Section I acronyms"
        rows.append({
            "document_id": doc_id,
            "section_structure": section_structure,
            "section_ii_narrowing_fired": narrowing_fired,
            "target_group": group,
            "rationale": rationale,
            "expected_to_benefit_from_d3a": "full" if group == "A_full_range_direct_target" else "partial",
        })

    OUT_CSV.write_text(
        "# v0.5 Unit D-3-A section-classification — 11 verified parser-dead-end docs.\n"
        "# target_group: A_full_range_direct_target (D-3-A directly admits Section I acronyms)\n"
        "#              B_narrowed_partial_benefit (only Section II acronyms reachable; Section I out-of-scope)\n"
        "# Generated from D-2 trace summaries (no PDF re-parse).\n"
    )
    with OUT_CSV.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["document_id", "section_structure", "section_ii_narrowing_fired", "target_group", "rationale", "expected_to_benefit_from_d3a"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    from collections import Counter
    groups = Counter(r["target_group"] for r in rows)
    print(f"section-classification: {dict(groups)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
