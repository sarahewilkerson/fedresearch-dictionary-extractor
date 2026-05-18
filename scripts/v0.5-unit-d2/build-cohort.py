"""A1 — build the 16-doc D-2 cohort from Unit-0 measurements + D-1 acceptance.

Reads two pinned upstream artifacts:
- validation_set/v0.5-unit0-measurements.tsv (rows with range_match='exact' → 11 Class-1 docs)
- validation_set/v0.5-unit-d1-acceptance.yaml (entries with disposition='deferred_to_d2' → 5 docs)

Emits validation_set/v0.5-unit-d2-cohort.csv with the union (16 entries).
Re-running produces byte-identical output (sorted by document_id).

Pinned to commit ed8ede5 (D-1 merge to main). The CSV header records the
source artifact commit for auditability.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
MEASUREMENTS_TSV = REPO_ROOT / "validation_set" / "v0.5-unit0-measurements.tsv"
ACCEPTANCE_YAML = REPO_ROOT / "validation_set" / "v0.5-unit-d1-acceptance.yaml"
UNIT0_COHORT_CSV = REPO_ROOT / "validation_set" / "v0.5-unit0-cohort.csv"
OUT_CSV = REPO_ROOT / "validation_set" / "v0.5-unit-d2-cohort.csv"
SOURCE_COMMIT = "ed8ede5"  # D-1 merge to main


def parse_acceptance_deferred() -> set[str]:
    """Parse the D-1 acceptance YAML for entries with disposition: deferred_to_d2."""
    text = ACCEPTANCE_YAML.read_text()
    deferred: set[str] = set()
    cur_id: str | None = None
    cur_disposition: str | None = None
    for line in text.splitlines():
        if line.startswith("  - document_id:"):
            if cur_id and cur_disposition == "deferred_to_d2":
                deferred.add(cur_id)
            cur_id = line.split(":", 1)[1].strip()
            cur_disposition = None
        elif cur_id and line.lstrip().startswith("disposition:"):
            cur_disposition = line.split(":", 1)[1].strip()
    if cur_id and cur_disposition == "deferred_to_d2":
        deferred.add(cur_id)
    return deferred


def main() -> int:
    # Class-1 from measurements (range_match='exact')
    class1: set[str] = set()
    with MEASUREMENTS_TSV.open() as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row["range_match"] == "exact":
                class1.add(row["document_id"])

    # D-1 deferred from acceptance YAML
    deferred = parse_acceptance_deferred()

    target_ids = class1 | deferred
    if len(target_ids) != 16:
        raise SystemExit(
            f"Expected 16 doc IDs (11 class-1 + 5 deferred); got {len(target_ids)}. "
            f"class1={len(class1)} deferred={len(deferred)}"
        )

    # Look up canonical_id + gcs_key + source_class from Unit-0 cohort
    canonical: dict[str, str] = {}
    gcs_keys: dict[str, str] = {}
    with UNIT0_COHORT_CSV.open() as f:
        for row in csv.DictReader(f):
            canonical[row["document_id"]] = row["canonical_id"]
            gcs_keys[row["document_id"]] = row["gcs_key"]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as out:
        # Header comment
        out.write("# v0.5 Unit D-2 cohort — 16 docs (11 Class-1 + 5 D-1-deferred)\n")
        out.write(f"# source_artifact_commit: {SOURCE_COMMIT}\n")
        out.write("# Re-run: python scripts/v0.5-unit-d2/build-cohort.py\n")
        writer = csv.DictWriter(out, fieldnames=["document_id", "canonical_id", "gcs_key", "source_class"])
        writer.writeheader()
        for doc_id in sorted(target_ids):
            writer.writerow({
                "document_id": doc_id,
                "canonical_id": canonical[doc_id],
                "gcs_key": gcs_keys[doc_id],
                "source_class": "class1" if doc_id in class1 else "d1_deferred",
            })
    print(f"wrote {OUT_CSV} ({len(target_ids)} entries)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
