"""
Canonical `normalize_term` algorithm shared with the FedResearch backend.

The TypeScript backend implements the SAME algorithm against the same fixture
(see `tests/fixtures/normalization_cases.yaml`). Drift between the two produces
silent exact-match failures at search time, so both implementations must agree
on every fixture case.

Algorithm (in order):
    1. NFKC Unicode normalization
    2. Replace curly quotes with straight ASCII quotes
    3. Remove periods and commas adjacent to uppercase letters (UCMJ normalize)
    4. Collapse hyphens at end-of-line (OCR'd hyphenation)
    5. Collapse all whitespace (incl. tabs/newlines) to single space
    6. Trim
    7. Lowercase
"""

import re
import unicodedata

_CURLY_SINGLE = {"‘", "’", "‚", "‛"}
_CURLY_DOUBLE = {"“", "”", "„", "‟"}

# Spec: "Remove periods and commas when adjacent to capital letters
# (U.C.M.J. → UCMJ, but 'e.g.,' at sentence end preserved)."
# A period or comma immediately PRECEDED by a capital letter is dropped,
# regardless of what follows. This catches:
#   - U.C.M.J. (between capitals)
#   - UCMJ. or UCMJ, at end-of-clause
#   - "the UCMJ, and" (capital then comma then lowercase) — the comma is not
#     part of the term, dropping it improves term-match correctness.
# Lowercase-adjacent punctuation (e.g., e.g., i.e.) is preserved because the
# lookbehind requires a capital letter.
_ACRONYM_PUNCT_RE = re.compile(r"(?<=[A-Z])[.,]")
# Strict: only collapse `-\n` with NO whitespace between (the canonical OCR
# line-break-hyphenation pattern). Hyphen + space + newline is preserved as
# intentional hyphenation in source text.
_HYPHEN_LINEBREAK_RE = re.compile(r"-\n")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_term(s: str) -> str:
    """
    Canonical term normalizer. Output is suitable as `term_normalized`
    and for equality-based Postgres lookup.

    >>> normalize_term("U.C.M.J.")
    'ucmj'
    >>> normalize_term("Combatant Command")
    'combatant command'
    >>> normalize_term("gover-\\nment")  # OCR line-break-hyphenation
    'government'
    >>> normalize_term("“Smart” quotes")
    '"smart" quotes'
    """
    if not s:
        return ""

    # 1. NFKC Unicode normalization
    out = unicodedata.normalize("NFKC", s)

    # 2. Curly quotes → straight quotes
    for ch in _CURLY_SINGLE:
        out = out.replace(ch, "'")
    for ch in _CURLY_DOUBLE:
        out = out.replace(ch, '"')

    # 3. Remove periods/commas when adjacent to uppercase letters
    #    (U.C.M.J. → UCMJ, but "e.g., " preserved because lowercase-adjacent)
    out = _ACRONYM_PUNCT_RE.sub("", out)

    # 4. Collapse hyphen-at-linebreak (gover-\nment → government)
    out = _HYPHEN_LINEBREAK_RE.sub("", out)

    # 5. Collapse all whitespace
    out = _WHITESPACE_RE.sub(" ", out)

    # 6. Trim
    out = out.strip()

    # 7. Lowercase
    return out.lower()
