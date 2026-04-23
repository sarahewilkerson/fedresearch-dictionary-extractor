"""
Text-cleaning utilities shared by glossary + inline extractors.

Ported from FedResearch_Dictionary_Creator (Jan 2026), adapted to remove
the patterns-module indirection and to expose a clean API.
"""

import re

import fitz

# OCR-spacing correction: "C o o p e r a t i v e" → "Cooperative"
_OCR_SPACED_CHARS_RE = re.compile(r"\b([A-Za-z] ){4,}[A-Za-z]\b")

# Gibberish detection constants
_MIN_GIBBERISH_LEN = 3
_VOWEL_THRESHOLD = 0.12
_MAX_WORD_LEN = 35
# PR1.2-quality fix: only match LOWERCASE consonant runs of 7+. Uppercase
# runs are nearly always acronyms (FTNGD, USINDOPACOM, NATO). Real English
# words can have 5-6 lowercase consonants in a row ("psychological",
# "twelfths", "strengths"); raising the threshold to 7 preserves them while
# still catching OCR garble like "kdjfghqp" or "mnnnbbpp". Pre-fix this
# wasn't an issue because shorter (often fragmented) definitions rarely
# tripped it; the new continuation-merge discipline produces full-length
# defs where common 5-consonant words like "psychology" appear regularly.
_CONSECUTIVE_CONSONANTS = re.compile(
    r"[bcdfghjklmnpqrstvwxyz]{7,}"
)
_DIGIT_IN_WORD = re.compile(r"[A-Za-z]\d[A-Za-z]|\d[A-Za-z]{4,}")


def fix_ocr_spacing(text: str) -> str:
    """'C o o p e r a t i v e' → 'Cooperative'."""

    def _collapse(m: re.Match[str]) -> str:
        return m.group(0).replace(" ", "")

    return _OCR_SPACED_CHARS_RE.sub(_collapse, text)


def is_gibberish(text: str) -> bool:
    """Heuristic detector for garbled OCR output."""
    if not text or len(text) < _MIN_GIBBERISH_LEN:
        return False

    clean = re.sub(r"[^\w\s]", "", text)

    if _CONSECUTIVE_CONSONANTS.search(clean):
        return True

    if _DIGIT_IN_WORD.search(clean):
        return True

    if text[0] in "$%*@#^~`¥|[]{}\\<>":
        return True

    alpha = [c for c in clean if c.isalpha()]
    if len(alpha) > 10:
        vowels = sum(1 for c in alpha if c.lower() in "aeiou")
        if vowels / len(alpha) < _VOWEL_THRESHOLD:
            return True

    return any(len(word) > _MAX_WORD_LEN for word in text.split())


def strip_citations(text: str, citation_pattern: str) -> str:
    """Remove profile-defined embedded citations from definition text."""
    cleaned = re.sub(citation_pattern, " ", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned.endswith(" ."):
        cleaned = cleaned[:-2] + "."
    return cleaned


def is_document_header(line: str, header_patterns: list[str]) -> bool:
    """True if the given line matches any of the profile's header/footer patterns."""
    for pattern in header_patterns:
        if re.search(pattern, line, re.IGNORECASE):
            return True
    return False


def is_span_bold(span: dict) -> bool:
    """
    True if a fitz/pymupdf text span is rendered bold.

    Checks both the bold flag (PDF spec bit 16 of `flags`) and the font name
    for hints — many PDFs synthesize bold via font choice without the flag.
    """
    font = (span.get("font") or "").lower()
    flags = int(span.get("flags") or 0)
    is_bold_flag = (flags & 16) > 0
    is_bold_font = "bold" in font or "black" in font or "heavy" in font
    return is_bold_flag or is_bold_font


def has_text_layer(doc: fitz.Document) -> bool:
    """
    True if the PDF has extractable text on a representative sample of pages.

    Samples up to 10 pages distributed across the document (front, middle, back),
    not just the first 5 — Army regulations frequently have image-only or
    near-empty front matter (cover, change-page, blank verso) followed by a real
    text body. A first-5-pages-only check produces false zero-entry classifications
    for those docs.

    Threshold: any sampled page with ≥100 characters of extracted text qualifies.
    """
    n = len(doc)
    if n == 0:
        return False
    # Build a deduped sample list: first 5, last 5, and 5 evenly-spaced from the middle.
    indices: set[int] = set()
    indices.update(range(min(5, n)))
    indices.update(range(max(0, n - 5), n))
    if n > 10:
        step = max(1, n // 6)
        indices.update(range(step, n - step, step))
    for i in sorted(indices):
        if len(doc[i].get_text().strip()) > 100:
            return True
    return False


def compute_text_sha256(doc: fitz.Document) -> str:
    """SHA-256 of the full extracted text. Used for idempotency keying."""
    import hashlib

    h = hashlib.sha256()
    for page in doc:
        h.update(page.get_text("text").encode("utf-8", errors="replace"))
    return h.hexdigest()
