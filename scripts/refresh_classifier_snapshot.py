#!/usr/bin/env python3
"""Regenerate validation_set/classifier_snapshot.yaml.

Reads every validation_set/candidate-output/*.json, runs classify() on each
entry, writes a deterministic snapshot YAML. Used as a committed regression
oracle per PR4-classifier plan §3.

Deterministic: no timestamps, entries sorted by (pdf, source_type, term).
Regenerating with unchanged inputs + unchanged classifier produces a
zero-line git diff.

Usage: python3 scripts/refresh_classifier_snapshot.py

The companion file `validation_set/classifier_snapshot_prefix.yaml` is
the immutable pre-fix baseline; this script does NOT touch it.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

# Allow `python scripts/refresh_classifier_snapshot.py` from repo root
# without requiring `pip install -e .` first.
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SRC_PATH = _REPO_ROOT / "src"
if _SRC_PATH.is_dir() and str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install -e '.[dev]'", file=sys.stderr)
    sys.exit(1)

from fedresearch_dictionary_extractor.labels_classifier import classify  # noqa: E402

CLASSIFIER_VERSION = "v2-2026-04-24"


def main() -> int:
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    cand_dir = repo_root / "validation_set" / "candidate-output"
    out_path = repo_root / "validation_set" / "classifier_snapshot.yaml"

    if not cand_dir.exists():
        print(f"ERROR: {cand_dir} not found", file=sys.stderr)
        return 1

    # Deterministic hash of the committed corpus (sorted paths + contents)
    h = hashlib.sha256()
    json_paths = sorted(cand_dir.glob("*.json"))
    for p in json_paths:
        h.update(p.name.encode("utf-8"))
        h.update(p.read_bytes())
    corpus_hash = f"sha256:{h.hexdigest()}"

    # Collect verdicts, sorted deterministically within each PDF
    docs: list[dict] = []
    for p in json_paths:
        data = json.loads(p.read_text(encoding="utf-8"))
        entries = data.get("entries", [])
        if not entries:
            continue
        verdicts = sorted(
            [
                {
                    "term": e["term"],
                    "source_type": e["source_type"],
                    "verdict": classify(e["term"], e["definition"]),
                }
                for e in entries
            ],
            key=lambda v: (v["source_type"], v["term"]),
        )
        docs.append({"pdf": p.name.replace(".json", ".pdf"), "verdicts": verdicts})

    # Sort docs by pdf name
    docs.sort(key=lambda d: d["pdf"])

    snapshot = {
        "classifier_version": CLASSIFIER_VERSION,
        "candidate_corpus_hash": corpus_hash,
        "entries": docs,
    }

    with open(out_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(snapshot, fh, sort_keys=False, default_flow_style=False, width=200)

    total_verdicts = sum(len(d["verdicts"]) for d in docs)
    good = sum(1 for d in docs for v in d["verdicts"] if v["verdict"] == "g")
    bad = total_verdicts - good
    print(f"Wrote {out_path.relative_to(repo_root)}")
    print(f"  {len(docs)} docs, {total_verdicts} verdicts ({good}g / {bad}b)")
    print(f"  classifier_version: {CLASSIFIER_VERSION}")
    print(f"  corpus_hash: {corpus_hash[:24]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
