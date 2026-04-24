#!/usr/bin/env python3
"""Regenerate tests/fixtures/option_b_expected_flips.yaml.

Reads FLIPS_BAD_TO_GOOD from scripts/build_labels_yaml.py, verifies each
override term is present in validation_set/candidate-output/*.json, and
writes a committed fixture. The fixture survives FLIPS_BAD_TO_GOOD being
pruned later in the same PR (Codex iter-4 #1) — the test pulls its truth
from this file, not from the mutable override dict.

Usage: python3 scripts/refresh_option_b_fixture.py

Run once in PR4-classifier §6 step 3; regenerate if FLIPS_BAD_TO_GOOD
changes before the prune.
"""
from __future__ import annotations

import json
import pathlib
import sys

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install -e '.[dev]'", file=sys.stderr)
    sys.exit(1)


def _load_flips_bad_to_good(build_script: pathlib.Path) -> dict[str, list[str]]:
    """Extract FLIPS_BAD_TO_GOOD dict from build_labels_yaml.py by exec-ing it.
    Provides `__file__` in the exec namespace so build_labels_yaml.py's
    sys.path shim (Codex remediation-iter-1) can resolve the repo root."""
    src = build_script.read_text(encoding="utf-8")
    # Guard against the if __name__ == "__main__" block + provide __file__
    # for the shim at the top of build_labels_yaml.py.
    module_ns: dict = {"__name__": "__not_main__", "__file__": str(build_script)}
    exec(compile(src, str(build_script), "exec"), module_ns)  # noqa: S102
    return module_ns["FLIPS_BAD_TO_GOOD"]


def main() -> int:
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    build_script = repo_root / "scripts" / "build_labels_yaml.py"
    cand_dir = repo_root / "validation_set" / "candidate-output"
    out_path = repo_root / "tests" / "fixtures" / "option_b_expected_flips.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    flips = _load_flips_bad_to_good(build_script)
    if not flips:
        # Post-PR-classifier-B steady state: FLIPS_BAD_TO_GOOD is empty
        # because Option B's rule tightenings made the overrides redundant.
        # The committed fixture (generated when the dict was populated) is
        # the canonical oracle. No-op exit.
        print(
            f"FLIPS_BAD_TO_GOOD is empty (expected post-PR-classifier-B). "
            f"Fixture at {out_path.relative_to(repo_root)} is unchanged.",
            file=sys.stderr,
        )
        return 0

    fixture_entries: list[dict] = []
    for pdf_prefix, terms in flips.items():
        json_paths = sorted(cand_dir.glob(f"{pdf_prefix}*.json"))
        if not json_paths:
            print(f"ERROR: no candidate-output for prefix {pdf_prefix!r}", file=sys.stderr)
            return 1
        entries_by_term: dict[str, dict] = {}
        for jp in json_paths:
            data = json.loads(jp.read_text(encoding="utf-8"))
            for e in data.get("entries", []):
                entries_by_term[e["term"]] = {
                    "source_type": e["source_type"],
                    "pdf": jp.name.replace(".json", ".pdf"),
                }
        for term in terms:
            if term not in entries_by_term:
                print(f"ERROR: override term not in corpus: {pdf_prefix}/{term!r}", file=sys.stderr)
                return 1
            meta = entries_by_term[term]
            fixture_entries.append(
                {
                    "pdf_prefix": pdf_prefix,
                    "pdf": meta["pdf"],
                    "source_type": meta["source_type"],
                    "term": term,
                }
            )

    fixture_entries.sort(key=lambda e: (e["pdf_prefix"], e["term"]))

    fixture = {
        "description": (
            "Terms that Option B's classifier fixes must flip from verdict 'b' "
            "to 'g'. Regenerate via: python3 scripts/refresh_option_b_fixture.py. "
            "Sourced from scripts/build_labels_yaml.py::FLIPS_BAD_TO_GOOD at the "
            "time this fixture was generated (independent of later dict pruning)."
        ),
        "expected_flips": fixture_entries,
    }

    with open(out_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(fixture, fh, sort_keys=False, default_flow_style=False, width=200, allow_unicode=True)

    print(f"Wrote {out_path.relative_to(repo_root)}")
    print(f"  {len(fixture_entries)} expected flips across {len(flips)} PDFs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
