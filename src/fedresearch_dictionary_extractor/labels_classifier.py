"""Heuristic classifier used to seed validation_set/labels.yaml entries.

Given an extracted (term, definition) pair from a candidate-output JSON,
`classify()` returns 'g' (good glossary entry) or 'b' (noise). The classifier
is a dev/validation tool only; it is NOT in the extractor wheel hot path.

This module exposes only pure functions — no I/O, no top-level side effects,
importable under `from fedresearch_dictionary_extractor.labels_classifier
import classify`.

This is the EXTRACTED module (step 2 of the plan); Option B rule fixes land
in step 4. Current behavior is bit-for-bit equivalent to the pre-extraction
in-script classifier at scripts/build_labels_yaml.py.
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


def looks_like_noun_phrase(t: str) -> bool:
    words = t.split()
    if not words or len(words) > 8:
        return False
    if re.search(r"\.\s+\S", t):
        return False
    if words[-1].lower().rstrip(".,;:") in STOP_TAIL:
        return False
    if sum(1 for c in t if c.isalpha() or c.isspace() or c in "-/") / max(len(t), 1) < 0.85:
        return False
    return True


def classify(term: str, definition: str) -> str:
    """Heuristic: 'g' (good glossary entry) or 'b' (noise)."""
    t = term.strip()
    d = definition.strip()
    if not t or not d: return "b"
    if t in NOISE_TERMS: return "b"
    if is_recognized_acronym_entry(t, d): return "g"
    if re.fullmatch(r"[A-Z]{6,}", t): return "b"
    if t.lower().startswith(("this section", "see ", "pin ")): return "b"
    if len(d) < 15: return "b"
    if t.startswith(("a. ", "b. ", "c. ", "(1)", "(2)", "(3)", "(4)", "(5)")): return "b"
    if re.search(r"\b(and|or|the|of|to|with|in|on|for|by|as|are|is|was|were|that|which|who)$", t, re.IGNORECASE):
        return "b"
    if len(t) > 80 or len(t) < 2: return "b"
    if re.fullmatch(r"[\d\.,\-/ ]+", t): return "b"
    if re.search(r"\([A-Z]{2,5}\s*$", t) or re.search(r"\(AR\b", t): return "b"
    if not looks_like_noun_phrase(t): return "b"
    if re.match(r"^(AR|PAM|FM|ATP|ADP|TC|TM|SD|STP)[\s\-]\d", d) and len(d) < 25:
        return "b"
    if re.fullmatch(r"[\d\.\)\s]+", d): return "b"
    return "g"
