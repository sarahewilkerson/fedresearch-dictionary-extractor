"""Corpus pin against committed candidate-output JSONs (Sub-Unit 1b).

This test verifies that committed validation_set/candidate-output/*.json files
no longer contain known-bad (term, definition_prefix_80) pairs reconciled
from labels-batch1.yaml.

It is NOT an extractor regression test — it does not invoke the extractor.
It pins the corpus state.

LIFECYCLE NOTE (PR-A of v0.3.0, 2026-04-27):
  Through Unit 5 of v0.2.0 (2026-04-26), this test asserted that the
  forbidden pairs WERE STILL PRESENT in candidate-output (assertion:
  ``forbidden in actual``). That captured the in-progress reality:
  Section II scoping (Unit 3) addressed a different bug class than the
  ones encoded in batch1_reconciled.yaml, so the bad pairs survived.

  PR-A of v0.3.0 ships extractor-level fixes for both forbidden pairs:
    - TC 1-19.30 'dampen \\nusually' → fix #1 (inline-regex sentence-boundary
      anchoring). The inline extractor will no longer match mid-sentence
      body fragments.
    - FM 3-34 '*field' → fix #2 (asterisk-prefix term strip). The leading
      '*' marker (Army "changed since previous publication" indicator) is
      now stripped before classification; the term will be emitted as
      'field' with flags=["changed_since_prior_pub"].

  The assertion is therefore FLIPPED to ``forbidden not in actual`` and
  marked xfail(strict=False) per pair. Today (committed v0.2.0
  candidate-output, prior to corpus regen): the test reports XFAIL —
  the bad pairs are still in the JSON files. After PR-A merges and the
  follow-up corpus-refresh task regenerates candidate-output under
  v0.3.0: the test reports XPASS, signalling the markers should be
  removed in a subsequent maintenance PR.

  strict=False is intentional: XPASS must be informational, not
  CI-breaking. We may regenerate candidate-output in a separate PR
  from the extractor-fix PR, and we don't want test failures during
  that gap.

See validation_set/batch1_reconciled.yaml for the data and
docs/plans/2026-04-27-pr-a-extractor-correctness-v0.3.0.md §3.1 for
the rationale behind the flip.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent / "validation_set"
RECONCILED = ROOT / "batch1_reconciled.yaml"
CANDIDATE_OUTPUT = ROOT / "candidate-output"

# Per-bug-class xfail reasons. Update when adding new pairs to the YAML.
_XFAIL_REASONS: dict[str, str] = {
    "page_footer_in_entries": (
        "inline-extractor over-match (TC 1-19.30 page-102 body fragment); "
        "addressed by PR-A v0.3.0 fix #1 (inline-regex sentence-boundary anchoring). "
        "XPASS fires after candidate-output is regenerated under v0.3.0."
    ),
    "asterisk_term_split": (
        "asterisk-prefix term split (FM 3-34 '*field'); "
        "addressed by PR-A v0.3.0 fix #2 (leading-'*' strip + flag). "
        "XPASS fires after candidate-output is regenerated under v0.3.0."
    ),
}


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


def _build_params() -> list:
    """Wrap each forbidden_pair in pytest.param with a per-bug-class xfail marker."""
    out = []
    for p in _load_pairs():
        bug_pattern = p.get("bug_pattern", "unknown")
        reason = _XFAIL_REASONS.get(
            bug_pattern,
            f"orthogonal bug class '{bug_pattern}' — no fix scheduled in PR-A",
        )
        case_id = f"{p['doc'].replace(' ', '_')}__{p['term'][:20].strip()}"
        out.append(
            pytest.param(
                p,
                marks=pytest.mark.xfail(strict=False, reason=reason),
                id=case_id,
            )
        )
    return out


_PARAMS = _build_params()


@pytest.mark.skipif(
    not _PARAMS, reason="batch1_reconciled.yaml not present or empty"
)
@pytest.mark.parametrize("pair", _PARAMS)
def test_forbidden_pair_no_longer_emitted(pair: dict) -> None:
    """Assert each forbidden (term, definition_prefix_80) pair is GONE from
    the committed candidate-output for its document. xfail today; XPASS
    after candidate-output regen post-PR-A.
    """
    out = _load_candidate(pair["doc"])
    forbidden = (pair["term"], pair["definition_prefix_80"])
    actual = {(e["term"], e["definition"][:80]) for e in out["entries"]}
    assert forbidden not in actual, (
        f"Forbidden pair {forbidden!r} STILL present in {pair['doc']!r} "
        f"candidate-output (bug class: {pair.get('bug_pattern')}). "
        f"This is the expected XFAIL state today (committed JSON predates "
        f"the fix). It will become XPASS after candidate-output is "
        f"regenerated under the extractor version that resolves this bug class."
    )
