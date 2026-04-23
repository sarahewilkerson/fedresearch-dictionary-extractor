"""
Inline-definition extractor.

Scans the full body text of a PDF for patterns like
"For purposes of this regulation, X means Y." and emits Entry dicts
matching schema v1 with `source_type: "inline"`.

v1 conservatism: confidence capped at 0.7, patterns intentionally narrow.
Backend tags inline rows as PENDING_REVIEW visibility by default.
"""
from __future__ import annotations

import re

import fitz

from ..normalize import normalize_term
from ..profiles.base import ReferenceProfile
from . import text as text_utils

_MIN_DEF_LEN = 10
_MAX_DEF_LEN = 1500


def extract_inline_definitions(doc: fitz.Document, profile: ReferenceProfile) -> list[dict]:
    """
    Walk every page, run profile.inline_definition_patterns against the page
    text, and emit a dict per match.
    """
    patterns = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in profile.inline_definition_patterns]
    out: list[dict] = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_text = text_utils.fix_ocr_spacing(page.get_text("text"))
        if not page_text or len(page_text) < 50:
            continue

        for r in patterns:
            for m in r.finditer(page_text):
                term = (m.group("term") or "").strip()
                definition = (m.group("definition") or "").strip()
                # PR1.2-quality: strip article/prefix noise from the term.
                # The first inline pattern's term group captures everything
                # between "purposes of this regulation," and "means" — which
                # includes leading "the term", "the word", "a", "an" prefixes.
                # Drop them so "the term healthcare" → "healthcare" (dedupes
                # with the second pattern's match).
                term = re.sub(r"^(?:the\s+(?:term|word|phrase|expression)\s+)", "", term, flags=re.IGNORECASE)
                term = re.sub(r"^(?:the|a|an)\s+", "", term, flags=re.IGNORECASE)
                term = term.strip(" '\"")
                if not term or not definition:
                    continue
                if len(definition) < _MIN_DEF_LEN or len(definition) > _MAX_DEF_LEN:
                    continue
                if text_utils.is_gibberish(definition):
                    continue
                definition_clean = text_utils.strip_citations(definition, profile.citation_pattern)
                out.append(
                    {
                        "term": term,
                        "term_normalized": normalize_term(term),
                        "definition": definition_clean,
                        "source_type": "inline",
                        "section": _guess_section(page_text),
                        "pdf_page_index": page_idx + 1,
                        "printed_page_label": _safe_label(doc, page_idx),
                        "confidence": 0.65,
                        "flags": ["inline_inferred"],
                    }
                )

    return out


def _safe_label(doc: fitz.Document, page_idx: int) -> str | None:
    try:
        label = doc[page_idx].get_label()
    except Exception:
        return None
    return label if label else None


_CHAPTER_RE = re.compile(r"\bChapter\s+([0-9]+|[IVX]+)\b", re.IGNORECASE)
_SECTION_RE = re.compile(r"\bSection\s+([A-Z0-9-]+)\b")


def _guess_section(page_text: str) -> str | None:
    """Best-effort section label from page text — Chapter N or Section X."""
    m = _CHAPTER_RE.search(page_text)
    if m:
        return f"Chapter {m.group(1)}"
    m = _SECTION_RE.search(page_text)
    if m:
        return f"Section {m.group(1)}"
    return None
