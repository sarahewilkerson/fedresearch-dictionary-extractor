"""Unit tests for src/fedresearch_dictionary_extractor/labels_classifier.py.

Covers:
- Option B 2a (parens-suffix noun phrases)
- Option B 2b (digit-prefix military abbreviations)
- Option B 2c (lowercase short-def abbreviations)
- Negative cases for each rule
- Import contract (module loadable without I/O)
- Expected-flip set (sourced from tests/fixtures/option_b_expected_flips.yaml —
  survives the prune of FLIPS_BAD_TO_GOOD in the same PR)
- No unexpected classifier flips (diffs snapshot_prefix.yaml vs snapshot.yaml
  and asserts the flip set equals the fixture)
"""
from __future__ import annotations

import json
import pathlib

import pytest
import yaml

from fedresearch_dictionary_extractor.labels_classifier import (
    _strip_trailing_parens,
    classify,
    is_digit_prefix_abbrev,
    is_recognized_acronym_entry,
    looks_like_noun_phrase,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CAND_DIR = REPO_ROOT / "validation_set" / "candidate-output"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "option_b_expected_flips.yaml"
SNAPSHOT = REPO_ROOT / "validation_set" / "classifier_snapshot.yaml"
SNAPSHOT_PREFIX = REPO_ROOT / "validation_set" / "classifier_snapshot_prefix.yaml"


# ── Option B 2a: parens-suffix noun phrases ────────────────────────────────

@pytest.mark.parametrize(
    "term,expected",
    [
        ("Active duty", "Active duty"),
        ("Foo (bar)", "Foo"),
        ("Foo (bar) (baz)", "Foo"),
        ("Foo (a) (b) (c)", "Foo"),
        ("Foo (a) (b) (c) (d)", "Foo (a)"),  # max_strips=3
        ("NoParensTerm", "NoParensTerm"),
    ],
)
def test_strip_trailing_parens(term: str, expected: str) -> None:
    assert _strip_trailing_parens(term) == expected


def test_looks_like_noun_phrase_10_word_limit() -> None:
    # 10 words OK (raised from 8)
    assert looks_like_noun_phrase("one two three four five six seven eight nine ten") is True
    # 11 words fails
    assert looks_like_noun_phrase("one two three four five six seven eight nine ten eleven") is False


def test_looks_like_noun_phrase_parens_stripped() -> None:
    # Long paren suffix: stripped core is short, passes
    term = "Medical treatment facility basic daily food allowance (MTF BDFA)"
    assert looks_like_noun_phrase(term) is True


# ── Option B 2b: digit-prefix military abbreviations ───────────────────────

@pytest.mark.parametrize("term", ["1LT", "2LT", "3LT", "1SG", "2SG"])
def test_is_digit_prefix_abbrev_accepts_military_ranks(term: str) -> None:
    assert is_digit_prefix_abbrev(term, "first lieutenant") is True


@pytest.mark.parametrize(
    "term",
    [
        "11B",       # MOS code (2 digits — intentionally rejected)
        "13F",       # MOS code
        "25U",       # MOS code
        "99ZZZ",     # bogus 2-digit prefix
        "1",         # too short
        "1A",        # too short (need 2+ letters)
        "LT",        # no digit
        "1LTXY",     # 4 letters — too many (regex caps at 3)
        "1lt",       # lowercase
    ],
)
def test_is_digit_prefix_abbrev_rejects(term: str) -> None:
    assert is_digit_prefix_abbrev(term, "some definition here") is False


def test_is_digit_prefix_abbrev_requires_def_min_length() -> None:
    # Def must be ≥ 3 chars
    assert is_digit_prefix_abbrev("1LT", "a") is False
    assert is_digit_prefix_abbrev("1LT", "abc") is True


# ── Option B 2c: lowercase short-def abbreviations ─────────────────────────

def test_classify_2c_lowercase_short_def_accepts() -> None:
    assert classify("vol", "voluntary") == "g"
    assert classify("pkg", "package") == "g"
    assert classify("ed", "education") == "g"


@pytest.mark.parametrize(
    "term,definition",
    [
        # uppercase single-word term with short def — 2c rejects, falls through
        # to `len(d) < 15` which rejects. (If CAR had a valid long def, the
        # acronym-override above would accept it — that's intentional.)
        ("Car", "tiny"),                     # uppercase-start + def < 15 → 'b'
        ("abcdef", "xyz"),                   # term too long for 2c (6 > 5); def too short (<15)
        ("word", "Word."),                   # def starts with uppercase → 2c rejects; def < 15 → 'b'
        ("ration", "."),                     # def too short (<3) for 2c; def < 15 → 'b'
    ],
)
def test_classify_2c_rejects(term: str, definition: str) -> None:
    # Each case fails the 2c allowance and also fails the standard short-def
    # path (len(d) < 15 after all overrides).
    assert classify(term, definition) == "b"


# ── Existing behavior preserved ────────────────────────────────────────────

@pytest.mark.parametrize(
    "term,definition",
    [
        ("UNCLASSIFIED", "PIN 060296-000"),
        ("SECTION II", "TERMS"),
        ("3 May 2013", "FM 3-55 Glossary-3"),
        ("This section contains no entries.", "DA PAM 350-58 • 8 March 2013 23"),
    ],
)
def test_classify_known_noise_still_rejected(term: str, definition: str) -> None:
    assert classify(term, definition) == "b"


def test_classify_known_good_still_accepted() -> None:
    assert classify(
        "Active duty",
        "Full-time duty in the active military Service of the United States.",
    ) == "g"
    # Acronym override: 6+ char acronym with alpha-start def
    assert classify("WHINSEC", "Western Hemisphere Institute for Security Cooperation") == "g"
    assert classify("TRADOC", "U.S. Army Training and Doctrine Command") == "g"


def test_is_recognized_acronym_entry() -> None:
    assert is_recognized_acronym_entry("WHINSEC", "Western Hemisphere Institute") is True
    assert is_recognized_acronym_entry("ASA (FM&C)", "Assistant Secretary of the Army") is True
    # Reject: lowercase-start
    assert is_recognized_acronym_entry("whinsec", "foo") is False
    # Reject: def too short
    assert is_recognized_acronym_entry("ABC", "ab") is False
    # Reject: def not alpha-start
    assert is_recognized_acronym_entry("ABC", "123 foo") is False


# ── Import contract ────────────────────────────────────────────────────────

def test_import_no_side_effects() -> None:
    """Module load must not perform I/O or emit output.
    Re-import and verify classify is callable without any setup."""
    import importlib

    import fedresearch_dictionary_extractor.labels_classifier as mod

    importlib.reload(mod)
    # Should be usable immediately
    assert mod.classify("Active duty", "Full-time military service of the United States.") == "g"


# ── Expected flip fixture (Codex iter-4 #1 — survives FLIPS_BAD_TO_GOOD prune) ──

def _load_fixture_entries() -> list[dict]:
    if not FIXTURE.exists():
        pytest.skip(f"fixture not present: {FIXTURE}")
    data = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    return data["expected_flips"]


def test_expected_flips_classify_good() -> None:
    """Every term in the committed fixture must classify as 'g'.

    Fixture was generated from FLIPS_BAD_TO_GOOD at step 3. Now that
    FLIPS_BAD_TO_GOOD has been pruned (step 6), the fixture is the
    sole source of truth for the expected flip set.
    """
    for flip in _load_fixture_entries():
        json_path = CAND_DIR / flip["pdf"].replace(".pdf", ".json")
        if not json_path.exists():
            pytest.skip(f"candidate-output not present: {json_path.name}")
        entries = json.loads(json_path.read_text(encoding="utf-8"))["entries"]
        matched = [
            e for e in entries
            if e["term"] == flip["term"] and e["source_type"] == flip["source_type"]
        ]
        assert matched, f"fixture term not found in corpus: {flip['pdf_prefix']}/{flip['term']!r}"
        verdict = classify(flip["term"], matched[0]["definition"])
        assert verdict == "g", (
            f"Option B expected 'g' for {flip['pdf_prefix']}/{flip['term']!r}, got {verdict!r}"
        )


# ── No unexpected classifier flips (Codex iter-4 #2 — dual snapshot diff) ──

def _load_snapshot(path: pathlib.Path) -> dict[tuple[str, str, str], str]:
    """Load a classifier_snapshot YAML into a {(pdf, source_type, term): verdict} map."""
    if not path.exists():
        pytest.skip(f"snapshot not present: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    out: dict[tuple[str, str, str], str] = {}
    for doc in data.get("entries", []):
        pdf = doc["pdf"]
        for v in doc["verdicts"]:
            out[(pdf, v["source_type"], v["term"])] = v["verdict"]
    return out


# Expected corpus removals over the baseline captured in
# classifier_snapshot_prefix.yaml. Each entry documents the removing PR +
# reason. Future corpus-shrinkage PRs must append to this set — exact-set
# equality on both directions makes silent drift impossible.
#
# `classifier_snapshot_prefix.yaml` remains IMMUTABLE (per
# validation_set/README.md) — its 700-entry keyspace captures pre-Option-B
# classifier behavior over the then-current corpus. When the CORPUS shrinks
# via extractor tightening (e.g., v0.2.a's invalid_term blocklist), the
# prefix snapshot doesn't lie; it just has "ghost" entries for terms that
# no longer exist, and this allowlist tracks them.
REMOVED_SINCE_PREFIX: set[tuple[str, str, str]] = {
    # v0.2.a (2026-04-24) — AR/FM pre-hyphen citation-fragment pattern
    (
        "AR_135-100_APPOINTMENT_OF_COMMISSIONED_AND_WARRANT_OFFICERS_"
        "OF_THE_ARMY_G-1_1994_09_01_OCR.pdf",
        "glossary",
        "AR 124",
    ),
    (
        "AR_135-100_APPOINTMENT_OF_COMMISSIONED_AND_WARRANT_OFFICERS_"
        "OF_THE_ARMY_G-1_1994_09_01_OCR.pdf",
        "glossary",
        "AR 140",
    ),
}


def test_no_unexpected_classifier_flips() -> None:
    """Diff classifier_snapshot.yaml (current) against classifier_snapshot_prefix.yaml
    (immutable pre-fix baseline). Asserts:
      - removed keyset == REMOVED_SINCE_PREFIX (tracks deliberate corpus
        shrinkage via extractor tightening)
      - added keyset == ∅ (unexpected corpus growth requires review)
      - b→g flips (on keys common to both) == fixture
      - no g→b regressions
    """
    prefix = _load_snapshot(SNAPSHOT_PREFIX)
    current = _load_snapshot(SNAPSHOT)

    removed = set(prefix.keys()) - set(current.keys())
    added = set(current.keys()) - set(prefix.keys())
    assert removed == REMOVED_SINCE_PREFIX, (
        f"unexpected_removed={removed - REMOVED_SINCE_PREFIX}, "
        f"missing_removed={REMOVED_SINCE_PREFIX - removed}"
    )
    assert not added, f"unexpected corpus growth (requires review): {added}"

    b_to_g: list[tuple[str, str, str]] = []
    g_to_b: list[tuple[str, str, str]] = []
    for key, pre_v in prefix.items():
        cur_v = current.get(key)
        if cur_v is None:
            continue  # removed entry — tracked by REMOVED_SINCE_PREFIX above
        if pre_v == "b" and cur_v == "g":
            b_to_g.append(key)
        elif pre_v == "g" and cur_v == "b":
            g_to_b.append(key)

    fixture = _load_fixture_entries()
    # Convert fixture to the snapshot key shape
    fixture_keys = {
        (f["pdf"], f["source_type"], f["term"]) for f in fixture
    }

    unexpected_b_to_g = set(b_to_g) - fixture_keys
    missing_b_to_g = fixture_keys - set(b_to_g)

    assert not g_to_b, f"unexpected g→b regressions: {g_to_b}"
    assert not unexpected_b_to_g, f"unexpected b→g flips not in fixture: {unexpected_b_to_g}"
    assert not missing_b_to_g, f"fixture flips not observed in snapshot diff: {missing_b_to_g}"
    assert len(b_to_g) == len(fixture_keys) == 12, \
        f"expected exactly 12 flips, got {len(b_to_g)} in snapshot / {len(fixture_keys)} in fixture"
