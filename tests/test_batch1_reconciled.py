"""Corpus pin against committed candidate-output JSONs (Sub-Unit 1b).

This test verifies that committed validation_set/candidate-output/*.json files
still contain known-bad (term, definition_prefix_80) pairs reconciled from
labels-batch1.yaml.

It is NOT an extractor regression test — it does not invoke the extractor.
The protection it provides is downstream: when Unit 3 fixes the extractor and
regenerates candidate-output, this test fails. The fix's PR must EITHER:
  (a) invert the assertion to `not in actual` (extractor-level fix landed),
  (b) replace this sentinel with fixture-based extractor tests + delete this
      file, OR
  (c) re-pin to a new known-bad pair if the corpus changed for unrelated
      reasons.

See validation_set/batch1_reconciled.yaml for the data and the
docs/plans/2026-04-26-batch1-reconciliation-ESCALATION.md for context.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent / "validation_set"
RECONCILED = ROOT / "batch1_reconciled.yaml"
CANDIDATE_OUTPUT = ROOT / "candidate-output"


def _load_pairs() -> list[dict]:
    if not RECONCILED.exists():
        return []
    data = yaml.safe_load(RECONCILED.read_text(encoding="utf-8")) or {}
    return data.get("forbidden_pairs", []) or []


def _load_candidate(doc: str) -> dict:
    """Find the single candidate-output JSON for `doc` matching `source_pub_number`,
    with `DA PAM ↔ PAM` normalization. Asserts exactly one match.
    """
    target_a = doc
    target_b = (
        doc.replace("PAM ", "DA PAM ", 1)
        if doc.startswith("PAM ") and not doc.startswith("DA PAM ")
        else doc
    )
    matches: list[tuple[str, dict]] = []
    for j in CANDIDATE_OUTPUT.glob("*.json"):
        try:
            d = json.loads(j.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        pub = d.get("source_pub_number")
        if pub in (target_a, target_b):
            matches.append((j.name, d))
    assert len(matches) == 1, (
        f"Expected exactly 1 candidate-output JSON for doc={doc!r}, "
        f"found {len(matches)}: {[m[0] for m in matches]}"
    )
    return matches[0][1]


_PAIRS = _load_pairs()


@pytest.mark.skipif(not _PAIRS, reason="batch1_reconciled.yaml not present or empty")
@pytest.mark.parametrize(
    "pair",
    _PAIRS,
    ids=lambda p: f"{p['doc'].replace(' ', '_')}__{p['term'][:20].strip()}",
)
def test_v0_1_0_corpus_pin_emits_known_forbidden_pair(pair: dict) -> None:
    out = _load_candidate(pair["doc"])
    forbidden = (pair["term"], pair["definition_prefix_80"])
    actual = {(e["term"], e["definition"][:80]) for e in out["entries"]}
    assert forbidden in actual, (
        f"Corpus pin broken: {pair['doc']!r} no longer emits forbidden pair "
        f"{forbidden!r}. This may signal:\n"
        f"  (a) candidate-output was regenerated under a fixed extractor "
        f"(intended outcome — flip assertion or replace with extractor-level "
        f"test per the file docstring), OR\n"
        f"  (b) candidate-output drift unrelated to extractor fix "
        f"(investigate before updating)."
    )
