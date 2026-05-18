"""A2 — capture v0.4 detected glossary ranges for the 11 Class-1 docs.

Runs `find_glossary_page_range` from the current code against each Class-1
doc PDF and emits YAML at `validation_set/v0.5-unit-d1-class1-range-preservation.yaml`.

Must be run on a worktree checked out at commit c4d1611 (v0.4.0). The
script asserts HEAD has glossary.py unchanged from c4d1611 to prevent
the baseline being captured from a mutated source state.
"""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).parent.parent.parent
COHORT_CSV = REPO_ROOT / "validation_set" / "v0.5-unit0-cohort.csv"
MEASUREMENTS_TSV = REPO_ROOT / "validation_set" / "v0.5-unit0-measurements.tsv"
PDF_DIR = Path("/tmp/v05-unit0/pdfs")
OUT_YAML = REPO_ROOT / "validation_set" / "v0.5-unit-d1-class1-range-preservation.yaml"
EXPECTED_V04_COMMIT = "c4d1611a98b8ec76c68b7faf02b4cd3e47b77511"


def assert_glossary_unchanged() -> str:
    """Verify glossary.py at HEAD matches glossary.py at c4d1611."""
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
            f"glossary.py has been modified since c4d1611. Cannot capture v0.4 baseline.\n"
            f"HEAD: {head_sha}\nDiff length: {len(diff)} chars"
        )
    return head_sha


def main() -> int:
    head_sha = assert_glossary_unchanged()
    print(f"glossary.py unchanged from {EXPECTED_V04_COMMIT}; HEAD={head_sha[:12]}", file=sys.stderr)

    # Import HERE so that import-time errors (e.g., HEAD has uncommitted glossary changes)
    # surface AFTER the assert.
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from fedresearch_dictionary_extractor.extractors.glossary import find_glossary_page_range
    from fedresearch_dictionary_extractor.profiles import get_profile

    # Load Class-1 doc IDs from measurements.tsv (range_match='exact')
    class1_ids: list[tuple[str, str]] = []
    with MEASUREMENTS_TSV.open() as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row["range_match"] == "exact":
                class1_ids.append((row["document_id"], row["canonical_id"]))
    print(f"Class-1 docs (exact range): {len(class1_ids)}", file=sys.stderr)

    # Look up gcs_key from cohort.csv
    gcs_keys: dict[str, str] = {}
    with COHORT_CSV.open() as f:
        for row in csv.DictReader(f):
            gcs_keys[row["document_id"]] = row["gcs_key"]

    profile = get_profile("army")
    entries = []
    for doc_id, canonical in class1_ids:
        gcs_key = gcs_keys[doc_id]
        pdf_basename = Path(gcs_key).name
        pdf_path = PDF_DIR / pdf_basename
        if not pdf_path.exists():
            raise SystemExit(f"PDF missing: {pdf_path}")
        doc = fitz.open(str(pdf_path))
        try:
            result = find_glossary_page_range(doc, profile)
            if result is None:
                raise SystemExit(
                    f"Class-1 doc {doc_id} returned None from find_glossary_page_range — "
                    f"contradicts measurements.tsv which classified it as 'exact'"
                )
            start, end = result
            entries.append({
                "document_id": doc_id,
                "canonical_id": canonical,
                "expected_start": start,
                "expected_end": end,
                "captured_from_commit": EXPECTED_V04_COMMIT,
            })
            print(f"  {doc_id[:12]}  range=({start}, {end})  {canonical[:60]}", file=sys.stderr)
        finally:
            doc.close()

    OUT_YAML.write_text(
        "# v0.5 Unit D-1: Class-1 docs (exact-range parser failures).\n"
        "# v0.4 reference ranges captured at commit c4d1611 (v0.4.0 release).\n"
        "# D-1 must preserve these ranges exactly; D-2 will trace parser dead-ends\n"
        "# starting from these pages.\n"
        f"# Captured by scripts/v0.5-unit-d1/capture-class1-ranges.py at HEAD={head_sha[:12]}.\n"
        "entries:\n"
        + "".join(
            f"  - document_id: {e['document_id']}\n"
            f"    canonical_id: {e['canonical_id']!r}\n"
            f"    expected_start: {e['expected_start']}\n"
            f"    expected_end: {e['expected_end']}\n"
            f"    captured_from_commit: {e['captured_from_commit']}\n"
            for e in entries
        )
    )
    print(f"\nWrote {OUT_YAML} ({len(entries)} entries)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
