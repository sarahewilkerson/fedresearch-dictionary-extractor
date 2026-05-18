"""A3 — build Class-2+3 acceptance YAML from Unit 0 measurements + simulated v0.5.

For each of the 27 Class-2+Class-3 doc IDs:
- Look up v0.4 detected range from measurements.tsv (detected_range_start/end).
- Compute the expected v0.5 range by running the FORWARD-SCAN-LARGEST-CONTIGUOUS
  algorithm on the PDF (simulated, not yet committed to glossary.py).
- Emit YAML with old_v04_range, expected_v05_range, acceptance_relation, etc.

The "expected" range is what v0.5's new logic SHOULD produce. Hand-confirmation
happens at PR review time; this script generates the proposal.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).parent.parent.parent
COHORT_CSV = REPO_ROOT / "validation_set" / "v0.5-unit0-cohort.csv"
MEASUREMENTS_TSV = REPO_ROOT / "validation_set" / "v0.5-unit0-measurements.tsv"
PDF_DIR = Path("/tmp/v05-unit0/pdfs")
OUT_YAML = REPO_ROOT / "validation_set" / "v0.5-unit-d1-acceptance.yaml"

sys.path.insert(0, str(REPO_ROOT / "src"))
from fedresearch_dictionary_extractor.profiles import get_profile

# Simulated v0.5 logic (will be ported to glossary.py in implementation phase)
def simulated_v05_find_glossary_range(doc: fitz.Document) -> tuple[int, int] | None:
    from fedresearch_dictionary_extractor.extractors.glossary import _GLOSSARY_END_PATTERNS, _is_back_cover_marker
    profile = get_profile("army")
    total = len(doc)
    header_res = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in profile.glossary_header_patterns]
    end_res = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in _GLOSSARY_END_PATTERNS]
    matching: list[int] = []
    for i in range(total):
        try:
            t = doc[i].get_text("text")
        except Exception:
            continue
        if any(r.search(t) for r in header_res):
            matching.append(i)
    if not matching:
        return None
    blocks: list[list[int]] = []
    cur = [matching[0]]
    for p in matching[1:]:
        if p == cur[-1] + 1:
            cur.append(p)
        else:
            blocks.append(cur)
            cur = [p]
    blocks.append(cur)
    blocks.sort(key=lambda b: (-len(b), b[0]))
    found_start = blocks[0][0]
    end = total - 1
    for i in range(found_start + 1, total):
        try:
            t = doc[i].get_text("text")
        except Exception:
            continue
        if any(r.search(t) for r in end_res):
            end = i - 1
            break
        if _is_back_cover_marker(t, i, total):
            end = i - 1
            break
    return (found_start, end)


def main() -> int:
    measurements = list(csv.DictReader(MEASUREMENTS_TSV.open(), delimiter="\t"))
    class23 = [r for r in measurements if r["range_match"] in ("overlap", "disjoint")]
    print(f"Class-2+3: {len(class23)}", file=sys.stderr)

    gcs_keys: dict[str, str] = {}
    canonical: dict[str, str] = {}
    with COHORT_CSV.open() as f:
        for row in csv.DictReader(f):
            gcs_keys[row["document_id"]] = row["gcs_key"]
            canonical[row["document_id"]] = row["canonical_id"]

    entries = []
    for row in class23:
        doc_id = row["document_id"]
        pdf = PDF_DIR / Path(gcs_keys[doc_id]).name
        if not pdf.exists():
            print(f"missing pdf: {pdf}", file=sys.stderr)
            continue
        doc = fitz.open(str(pdf))
        try:
            v05 = simulated_v05_find_glossary_range(doc)
        finally:
            doc.close()
        old = [int(row["detected_range_start"]), int(row["detected_range_end"])] if row["detected_range_start"] != "None" else None
        new = list(v05) if v05 else None
        known = [int(row["known_range_start"]), int(row["known_range_end"])] if row["known_range_start"] != "None" else None
        entries.append({
            "document_id": doc_id,
            "canonical_id": canonical[doc_id],
            "old_v04_range": old,
            "loose_heuristic_range": known,
            "expected_v05_range": new,
            "acceptance_relation": "exact",
            "expected_entry_count_min": 1,
            "disposition": "active",
        })
        print(f"  {doc_id[:12]}  v04={old}  loose={known}  v0.5_simulated={new}", file=sys.stderr)

    OUT_YAML.write_text(
        "# v0.5 Unit D-1: Class-2 + Class-3 docs acceptance YAML.\n"
        "# 27 docs where v0.4's find_glossary_page_range returned an incorrect range.\n"
        "# expected_v05_range is what the simulated v0.5 forward-scan-largest-block\n"
        "# algorithm produces; hand-confirmation at PR review time.\n"
        "# acceptance_relation: 'exact' is the default; per-doc relaxation requires\n"
        "# a documented rationale string.\n"
        "# disposition: 'active' (in-scope) | 'deferred_to_d2' | 'scope_decision' |\n"
        "#              'known_failure_with_followup_unit'. No anonymous failures.\n\n"
        "entries:\n"
        + "".join(
            f"  - document_id: {e['document_id']}\n"
            f"    canonical_id: {e['canonical_id']!r}\n"
            f"    old_v04_range: {e['old_v04_range']}\n"
            f"    loose_heuristic_range: {e['loose_heuristic_range']}\n"
            f"    expected_v05_range: {e['expected_v05_range']}\n"
            f"    acceptance_relation: {e['acceptance_relation']}\n"
            f"    expected_entry_count_min: {e['expected_entry_count_min']}\n"
            f"    disposition: {e['disposition']}\n"
            for e in entries
        )
    )
    print(f"\nWrote {OUT_YAML} ({len(entries)} entries)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
