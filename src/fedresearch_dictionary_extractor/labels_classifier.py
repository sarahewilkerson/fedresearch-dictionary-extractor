"""Heuristic classifier used to seed validation_set/labels.yaml entries.

Given an extracted (term, definition) pair from a candidate-output JSON,
`classify()` returns 'g' (good glossary entry) or 'b' (noise). The classifier
is a dev/validation tool only; it is NOT in the extractor wheel hot path.

This module exposes only pure functions — no I/O, no top-level side effects,
importable under `from fedresearch_dictionary_extractor.labels_classifier
import classify`.

Option B rule families (from PR4-classifier plan §2):

- 2a: `looks_like_noun_phrase` strips up to 3 trailing `( ... )` paren groups
  before the word-count check, and the word-count limit is 10 (was 8). Catches
  `Medical treatment facility basic daily food allowance (MTF BDFA)`,
  `Pharmacy data transaction service (PDTS) (from PDTS Business Rules)`.
- 2b: `is_digit_prefix_abbrev` — 1 digit + 2-3 letters. Recognizes military
  rank abbreviations like `1LT`, `2LT`, `1SG`. Intentionally rejects MOS
  codes `11B` (2 digits) which are not typical glossary headwords.
- 2c: in `classify`, `len(d) < 15` is relaxed for 2-5 lowercase letter terms
  paired with lowercase noun-phrase definitions. Catches `vol → voluntary`.
"""
from __future__ import annotations

import re

NOISE_TERMS: set[str] = {
    "UNCLASSIFIED",
    "CLASSIFIED",
    "CONFIDENTIAL",
    "SECRET",
    "This section contains no entries.",
    "Terms",
    "See",
}
STOP_TAIL: set[str] = {
    "and", "or", "the", "of", "to", "with", "in", "on", "for", "by", "as",
    "are", "is", "was", "were", "that", "which", "who", "if", "when",
}
ACRO_TERM_RE = re.compile(r"^[A-Z][A-Z0-9.\-/]{1,18}(\s*\([^)]{1,20}\))?$")


def is_recognized_acronym_entry(term: str, definition: str) -> bool:
    """Recognized acronym + expansion pattern (e.g., WHINSEC, SECARMY,
    ASA (FM&C)). Override for the `^[A-Z]{6,}` rule."""
    if not term or not definition or len(term) > 22:
        return False
    if not ACRO_TERM_RE.match(term):
        return False
    if not definition[0].isalpha() or len(definition) < 3:
        return False
    return True


# Option B 2b: military rank abbreviations. Exactly 1 digit + 2-3 letters.
# Matches 1LT, 2LT, 3LT, 1SG, 2SG. Intentionally rejects MOS codes like
# 11B, 13F, 25U (start with 2 digits, not typical glossary headwords).
_DIGIT_PREFIX_ABBREV_RE = re.compile(r"^\d[A-Z]{2,3}$")


def is_digit_prefix_abbrev(term: str, definition: str) -> bool:
    """Military rank abbreviations: 1LT, 2LT, 3LT, 1SG, 2SG."""
    if not _DIGIT_PREFIX_ABBREV_RE.match(term):
        return False
    if not definition or len(definition.strip()) < 3:
        return False
    return True


# Option B 2a: strip up to 3 trailing balanced `( ... )` groups before the
# noun-phrase word-count check. Handles multi-paren cases like
# `Pharmacy data transaction service (PDTS) (from PDTS Business Rules)`.
_TRAILING_PAREN_RE = re.compile(r"\s*\([^()]{1,120}\)\s*$")


def _strip_trailing_parens(t: str, max_strips: int = 3) -> str:
    """Peel up to `max_strips` trailing balanced-flat `( ... )` groups.
    Balanced-flat constraint (`[^()]` inside) means nested parens are NOT
    handled — term falls through to the regular noun-phrase check."""
    current = t.rstrip()
    for _ in range(max_strips):
        stripped = _TRAILING_PAREN_RE.sub("", current)
        if stripped == current:
            break
        current = stripped.rstrip()
    return current


def looks_like_noun_phrase(t: str) -> bool:
    # Option B 2a: strip trailing paren groups before word-count check.
    core = _strip_trailing_parens(t)
    words = core.split()
    # Option B 2a: allow 10-word phrases (was 8) for medical/technical terms.
    if not words or len(words) > 10:
        return False
    if re.search(r"\.\s+\S", core):
        return False
    if words[-1].lower().rstrip(".,;:") in STOP_TAIL:
        return False
    if sum(1 for c in core if c.isalpha() or c.isspace() or c in "-/") / max(len(core), 1) < 0.85:
        return False
    return True


# Option B 2c: lowercase short-def abbreviations (vol → voluntary). Targets
# lowercase-start-lowercase-expansion patterns only; uppercase-start acronyms
# go through is_recognized_acronym_entry.
_LOWERCASE_SHORT_TERM_RE = re.compile(r"^[a-z]{2,5}$")
_LOWERCASE_SHORT_DEF_RE = re.compile(r"^[a-z][a-z ]{2,49}$")


def classify(term: str, definition: str) -> str:
    """Heuristic: 'g' (good glossary entry) or 'b' (noise)."""
    t = term.strip()
    d = definition.strip()
    if not t or not d:
        return "b"
    if t in NOISE_TERMS:
        return "b"
    if is_recognized_acronym_entry(t, d):
        return "g"
    # Option B 2b: military rank abbreviations (1LT, 2LT, 1SG).
    if is_digit_prefix_abbrev(t, d):
        return "g"
    # Remaining `^[A-Z]{6,}` rule is reached only when is_recognized_acronym_entry
    # returns False — i.e., def is non-alpha-start or <3 chars. Genuine garbage
    # like raw `UNCLASSIFIED`/`CONFIDENTIAL` with PIN-only defs.
    if re.fullmatch(r"[A-Z]{6,}", t):
        return "b"
    if t.lower().startswith(("this section", "see ", "pin ")):
        return "b"
    if len(d) < 15:
        # Option B 2c: lowercase short-def abbreviations (e.g., vol → voluntary).
        # 2-5 lowercase letter term + lowercase noun-phrase def 3-50 chars.
        # Uppercase-start acronyms go through is_recognized_acronym_entry above.
        if _LOWERCASE_SHORT_TERM_RE.match(t) and _LOWERCASE_SHORT_DEF_RE.match(d):
            return "g"
        return "b"
    if t.startswith(("a. ", "b. ", "c. ", "(1)", "(2)", "(3)", "(4)", "(5)")):
        return "b"
    if re.search(
        r"\b(and|or|the|of|to|with|in|on|for|by|as|are|is|was|were|that|which|who)$",
        t,
        re.IGNORECASE,
    ):
        return "b"
    # Option B 2a length cap: use post-strip core for upper bound so
    # long-paren-suffix terms aren't rejected before looks_like_noun_phrase
    # peels their trailing parens. 100 chars accommodates ~10 ten-char words.
    if len(t) < 2:
        return "b"
    if len(_strip_trailing_parens(t)) > 100:
        return "b"
    if re.fullmatch(r"[\d\.,\-/ ]+", t):
        return "b"
    if re.search(r"\([A-Z]{2,5}\s*$", t) or re.search(r"\(AR\b", t):
        return "b"
    if not looks_like_noun_phrase(t):
        return "b"
    if re.match(r"^(AR|PAM|FM|ATP|ADP|TC|TM|SD|STP)[\s\-]\d", d) and len(d) < 25:
        return "b"
    if re.fullmatch(r"[\d\.\)\s]+", d):
        return "b"
    return "g"
