"""Corpus-refresh integration tests for v0.2.a (pre-hyphen citation blocklist).

Compares post-fix candidate-output against the committed pre-fix snapshot
(tests/fixtures/v0_2_a_pre_fix_snapshot.json) to enforce:

- §3e Predecessor-def byte-equality against hand-derived fixture
- §3f Exact removed-set (only AR 124, AR 140)
- §3f-bis Surviving-entry byte-invariant (all other entries unchanged at
         field level — ignoring top-level metadata like extraction_timestamp)
- §3g PAM_71-32 byte-identical (Equip for deferred to v0.2.b)

Plan: docs/plans/2026-04-24-invalid-term-blocklist.md
"""
from __future__ import annotations

import json
import pathlib

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CAND_DIR = REPO_ROOT / "validation_set" / "candidate-output"
PRE_FIX_SNAPSHOT = REPO_ROOT / "tests" / "fixtures" / "v0_2_a_pre_fix_snapshot.json"
PREDECESSOR_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "v0_2_a_predecessor_defs.yaml"

AR_135_PDF = "AR_135-100_APPOINTMENT_OF_COMMISSIONED_AND_WARRANT_OFFICERS_OF_THE_ARMY_G-1_1994_09_01_OCR.json"
PAM_71_PDF = "PAM_71-32_FORCE_DEVELOPMENT_AND_DOCUMENTATION_CONSOLIDATED_PROCEDURES_G-3_5_7_2019_03_21_OCR.json"

EXPECTED_REMOVED = {
    f"{AR_135_PDF}::glossary::AR 124",
    f"{AR_135_PDF}::glossary::AR 140",
}


def _load_pre_fix_snapshot() -> dict[str, dict]:
    return json.loads(PRE_FIX_SNAPSHOT.read_text(encoding="utf-8"))


def _collect_post_fix_entries() -> dict[str, dict]:
    post_fix: dict[str, dict] = {}
    for jp in sorted(CAND_DIR.glob("*.json")):
        data = json.loads(jp.read_text(encoding="utf-8"))
        for e in data.get("entries", []):
            key = f'{jp.name}::{e["source_type"]}::{e["term"]}'
            post_fix[key] = {
                "definition": e["definition"],
                "section": e.get("section"),
                "pdf_page_index": e["pdf_page_index"],
                "printed_page_label": e.get("printed_page_label"),
                "confidence": e.get("confidence"),
                "flags": e.get("flags", []),
            }
    return post_fix


# ── §3f: removed-set equals exactly the 2 expected AR fragments ───────────

def test_removed_set_equals_expected() -> None:
    """Only AR 124 and AR 140 should disappear from the corpus."""
    pre_fix = _load_pre_fix_snapshot()
    post_fix = _collect_post_fix_entries()
    removed = set(pre_fix.keys()) - set(post_fix.keys())
    added = set(post_fix.keys()) - set(pre_fix.keys())
    assert removed == EXPECTED_REMOVED, (
        f"unexpected_removed={removed - EXPECTED_REMOVED}, "
        f"missing_removed={EXPECTED_REMOVED - removed}"
    )
    assert added == set(), f"unexpected entries added: {added}"


# ── §3e: predecessor-def byte-equal to hand-derived fixture ───────────────

def test_predecessor_defs_match_fixture() -> None:
    """Predecessor definitions must byte-equal the hand-derived fixture
    (captured BEFORE re-extraction, so this is not tautological)."""
    fixture = yaml.safe_load(PREDECESSOR_FIXTURE.read_text(encoding="utf-8"))
    for spec in fixture["expected"]:
        path = CAND_DIR / spec["pdf"]
        data = json.loads(path.read_text(encoding="utf-8"))
        match = next(
            (e for e in data["entries"] if e["term"] == spec["term"]),
            None,
        )
        assert match is not None, f"predecessor missing from corpus: {spec['term']!r}"
        assert match["definition"] == spec["expected_definition"], (
            f"{spec['term']!r} def mismatch:\n"
            f"  expected: {spec['expected_definition']!r}\n"
            f"  actual:   {match['definition']!r}"
        )


# ── §3f-bis: surviving-entry byte-invariant at field level ─────────────────

def test_surviving_entries_field_invariant() -> None:
    """Every non-removed entry must be field-equal to its pre-fix content,
    EXCEPT the 2 predecessor entries whose defs legitimately changed."""
    pre_fix = _load_pre_fix_snapshot()
    post_fix = _collect_post_fix_entries()
    fixture = yaml.safe_load(PREDECESSOR_FIXTURE.read_text(encoding="utf-8"))
    predecessor_keys = {
        f'{spec["pdf"]}::glossary::{spec["term"]}'
        for spec in fixture["expected"]
    }

    overlap = set(pre_fix.keys()) & set(post_fix.keys())
    mutated: list[str] = []
    for key in overlap:
        if key in predecessor_keys:
            continue  # legitimate change tracked by fixture test
        if pre_fix[key] != post_fix[key]:
            mutated.append(key)
    assert not mutated, (
        f"{len(mutated)} non-predecessor entries mutated unexpectedly: "
        f"{mutated[:10]}{'...' if len(mutated) > 10 else ''}"
    )


# ── §3g: PAM_71-32 unchanged (Equip for deferred to v0.2.b) ────────────────

def test_pam_71_32_entries_unchanged() -> None:
    """No entry-level changes in PAM_71-32 — Equip for case deferred to v0.2.b.

    Compares entry field content only (ignores top-level metadata like
    extraction_timestamp which updates on every re-extraction)."""
    pre_fix = _load_pre_fix_snapshot()
    post_fix = _collect_post_fix_entries()

    pre_pam = {k: v for k, v in pre_fix.items() if k.startswith(f"{PAM_71_PDF}::")}
    post_pam = {k: v for k, v in post_fix.items() if k.startswith(f"{PAM_71_PDF}::")}

    assert set(pre_pam.keys()) == set(post_pam.keys()), (
        f"PAM_71-32 entry keyset changed: "
        f"removed={set(pre_pam.keys()) - set(post_pam.keys())}, "
        f"added={set(post_pam.keys()) - set(pre_pam.keys())}"
    )
    mutated = [k for k in pre_pam if pre_pam[k] != post_pam[k]]
    assert not mutated, f"PAM_71-32 entries mutated: {mutated}"


# ── Sanity: Equip for still in PAM_71-32 (deferred to v0.2.b) ──────────────

def test_equip_for_still_present_pending_v0_2_b() -> None:
    """Explicit assertion that 'Equip for' remains in PAM_71-32, since
    v0.2.a intentionally does NOT fix it (deferred to v0.2.b)."""
    data = json.loads((CAND_DIR / PAM_71_PDF).read_text(encoding="utf-8"))
    terms = [e["term"] for e in data["entries"]]
    assert "Equip for" in terms, (
        "'Equip for' unexpectedly removed from PAM_71-32. "
        "v0.2.a should leave it alone (deferred to v0.2.b). "
        "If this was intentional, update the plan + EXCLUDE_FROM_NEGATIVES."
    )
