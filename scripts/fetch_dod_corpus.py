"""Re-fetch the P2-B DoD validation corpus from GCS per the manifest.

PDFs are gitignored (validation_set/dod_pdfs/); this restores them for the
`-m validation` tests. Requires gsutil + GCS auth for the docs bucket (on the
Hetzner host the SA is at /etc/fedresearch/gcs-sa.json).

    python scripts/fetch_dod_corpus.py --dry-run        # list gcs keys
    python scripts/fetch_dod_corpus.py                  # fetch + verify sha256
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).parent.parent
MANIFEST = REPO / "validation_set" / "dod-corpus-manifest.yaml"
PDF_DIR = REPO / "validation_set" / "dod_pdfs"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    m = yaml.safe_load(MANIFEST.read_text())
    bucket = m["bucket"]
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    rc = 0
    for doc in m["docs"]:
        gcs = f"gs://{bucket}/{doc['gcs_key']}"
        dest = PDF_DIR / doc["local"]
        if args.dry_run:
            print(f"{doc['family']:10} {gcs}")
            continue
        subprocess.run(["gsutil", "-q", "cp", gcs, str(dest)], check=True)
        sha = hashlib.sha256(dest.read_bytes()).hexdigest()
        ok = sha.startswith(doc["sha256_prefix"])
        print(f"{'OK ' if ok else 'BAD'} {doc['local']} sha={sha[:16]}")
        rc |= 0 if ok else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
