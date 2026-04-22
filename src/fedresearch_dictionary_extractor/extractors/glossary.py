"""
Glossary detection + parsing for Army-style regulations.

Strategy (same as the original FedResearch_Dictionary_Creator, adapted to emit
dicts matching schema v1 rather than DOCX entries):

1. Scan from the end of the PDF backward, looking for a glossary header
   (profile.glossary_header_patterns).
2. Extend backward to find the true start of the section.
3. Scan forward from the found start, collecting term/definition pairs
   until Index / References / Appendix / end-of-document.
4. For each page in the glossary, parse visually: group text spans by
   Y-coordinate, detect the term-column X threshold, split terms vs
   continuation lines.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

import fitz

from ..normalize import normalize_term
from ..profiles.base import ReferenceProfile
from . import text as text_utils

if TYPE_CHECKING:
    pass

# Heuristic thresholds
_MAX_HEADER_Y = 150  # ignore text above this Y (page header)
_TERM_COL_MARGIN = 30  # points past min_x before text is a "continuation"
_MAX_GLOSSARY_LOOKBACK_PAGES = 30
_MIN_TERM_LEN = 2
_MAX_TERM_LEN = 100
_MAX_DEFINITION_LEN = 5000
_GLOSSARY_END_PATTERNS = (
    r"^\s*Index\s*(\n|$)",
    r"^\s*References\s*(\n|$)",
    r"^\s*Appendix\s+[A-Z]",
    r"^\s*Bibliography\s*(\n|$)",
)


def find_glossary_page_range(doc: fitz.Document, profile: ReferenceProfile) -> tuple[int, int] | None:
    """
    Return (start_page_index, end_page_index) inclusive, or None if no
    glossary found. Indices are 0-based (pymupdf native).
    """
    total = len(doc)
    header_res = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in profile.glossary_header_patterns]
    end_res = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in _GLOSSARY_END_PATTERNS]

    # Walk backward, find the last page with a glossary header.
    found_start = None
    for i in range(total - 1, max(-1, total - _MAX_GLOSSARY_LOOKBACK_PAGES - 1), -1):
        page_text = doc[i].get_text("text")
        for r in header_res:
            if r.search(page_text):
                found_start = i
                break
        if found_start is not None:
            break

    if found_start is None:
        return None

    # Walk forward to find the end (Index / Appendix / etc.).
    end = total - 1
    for i in range(found_start + 1, total):
        page_text = doc[i].get_text("text")
        if any(r.search(page_text) for r in end_res):
            end = i - 1
            break

    return (found_start, end)


def _extract_lines(page: fitz.Page) -> list[tuple[float, float, str]]:
    """
    Return [(y, min_x, line_text), ...] for the page.
    Groups spans by approximate Y coordinate (tolerance 2.0).
    """
    spans: list[tuple[float, float, str]] = []  # (y, x, text)
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                bbox = span["bbox"]
                y = round(bbox[1], 0)
                x = bbox[0]
                t = span.get("text", "").strip()
                if t and y > _MAX_HEADER_Y:
                    spans.append((y, x, t))

    # Group spans into lines by Y (tolerance 2.0)
    if not spans:
        return []

    spans.sort(key=lambda s: (s[0], s[1]))
    out: list[tuple[float, float, str]] = []
    cur_y = spans[0][0]
    cur_min_x = spans[0][1]
    cur_parts: list[str] = [spans[0][2]]
    for y, x, t in spans[1:]:
        if abs(y - cur_y) <= 2.0:
            cur_parts.append(t)
            cur_min_x = min(cur_min_x, x)
        else:
            out.append((cur_y, cur_min_x, " ".join(cur_parts)))
            cur_y = y
            cur_min_x = x
            cur_parts = [t]
    out.append((cur_y, cur_min_x, " ".join(cur_parts)))
    return out


def parse_glossary_entries(
    doc: fitz.Document,
    start: int,
    end: int,
    profile: ReferenceProfile,
) -> list[dict]:
    """
    Walk pages [start, end] inclusive, producing dict entries matching the
    Entry schema (minus backend-assigned fields like visibility).
    """
    invalid_res = [re.compile(p) for p in profile.invalid_term_patterns]
    header_res = [re.compile(p, re.IGNORECASE) for p in profile.header_patterns]
    # Match lines like "Term. Definition..." or "Term — Definition"
    split_re = re.compile(
        r"^(?P<term>[A-Za-z0-9][A-Za-z0-9\-\.\s/\(\)]{0,50}?)"
        r"(?:\s*\.\s+|\s+[—–-]\s+)"
        r"(?P<def>[A-Z\"(][^\n]{5,})"
    )

    entries: list[dict] = []
    current_term: str | None = None
    current_def_parts: list[str] = []
    current_page: int | None = None

    def _is_header(line: str) -> bool:
        return any(r.search(line) for r in header_res)

    def _is_invalid_term(term: str) -> bool:
        if len(term) < _MIN_TERM_LEN or len(term) > _MAX_TERM_LEN:
            return True
        return any(r.match(term) for r in invalid_res)

    def _flush(page_for_flush: int | None) -> None:
        nonlocal current_term, current_def_parts, current_page
        if current_term and current_def_parts:
            definition = " ".join(current_def_parts).strip()
            definition = text_utils.strip_citations(definition, profile.citation_pattern)
            if 1 <= len(definition) <= _MAX_DEFINITION_LEN and not text_utils.is_gibberish(definition):
                page_idx = page_for_flush if page_for_flush is not None else (current_page or start)
                entries.append(
                    {
                        "term": current_term.strip(),
                        "term_normalized": normalize_term(current_term),
                        "definition": definition,
                        "source_type": "glossary",
                        "section": "Glossary",
                        "pdf_page_index": page_idx + 1,  # convert 0-indexed → 1-indexed
                        "printed_page_label": _safe_page_label(doc, page_idx),
                        "confidence": 0.95,
                        "flags": [],
                    }
                )
        current_term = None
        current_def_parts = []
        current_page = None

    for page_idx in range(start, end + 1):
        page = doc[page_idx]
        lines = _extract_lines(page)
        if not lines:
            continue

        min_x = min(lx for _, lx, _ in lines)
        term_threshold = min_x + _TERM_COL_MARGIN

        for _y, x, raw_text in lines:
            raw_text = text_utils.fix_ocr_spacing(raw_text).strip()
            if not raw_text or _is_header(raw_text):
                continue

            # Inline "term. definition" on one line
            m = split_re.match(raw_text)
            if m:
                _flush(current_page)
                term = m.group("term").strip()
                if not _is_invalid_term(term):
                    current_term = term
                    current_def_parts = [m.group("def").strip()]
                    current_page = page_idx
                continue

            # New term: starts at (or close to) left margin
            if x <= term_threshold and not raw_text[0].islower():
                _flush(current_page)
                if not _is_invalid_term(raw_text):
                    current_term = raw_text
                    current_def_parts = []
                    current_page = page_idx
            else:
                # Continuation of current definition
                if current_term is not None:
                    current_def_parts.append(raw_text)

    _flush(current_page)
    return entries


def _safe_page_label(doc: fitz.Document, page_idx: int) -> str | None:
    """pymupdf's page.get_label() returns '' when unset; normalize to None."""
    try:
        label = doc[page_idx].get_label()
    except Exception:
        return None
    return label if label else None
