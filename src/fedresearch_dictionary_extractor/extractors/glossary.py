"""
Glossary detection + parsing for Army-style regulations.

Strategy:

1. Scan from the end of the PDF backward, looking for a glossary header
   (profile.glossary_header_patterns).
2. Extend backward to find the true start of the section (first occurrence
   in the backward sweep).
3. Scan forward from the found start, collecting term/definition pairs
   until Index / References / Appendix / end-of-document.
4. For each page in the glossary, parse visually:
     - Group all spans by Y-coordinate to recover physical lines.
     - Filter out top-of-page header zone via profile.header_patterns.
     - Filter invalid candidate lines via profile.invalid_term_patterns.
     - Determine "term column" as min_x + TERM_COL_MARGIN.
     - For each line: if its leftmost span is in the term column AND the
       span passes term-validation, treat it as a NEW term — flushing the
       previous (term, accumulated def lines) into entries first.
     - All other lines (or lines whose validation fails) accumulate into
       the current definition.

The validation-before-flush discipline is critical: a continuation line
that happens to start at the left margin must NOT split the previous
term's definition. Earlier port versions flushed unconditionally on any
left-margin line, which broke real-PDF extraction. This implementation
ports the working logic from the source FedResearch_Dictionary_Creator
project.
"""
from __future__ import annotations

import re

import fitz

from ..normalize import normalize_term
from ..profiles.base import ReferenceProfile
from . import text as text_utils

# ── Heuristic thresholds ──────────────────────────────────────────────────
HEADER_ZONE_Y = 150              # ignore document headers above this Y
FOOTER_ZONE_PCT = 0.88           # bottom 12% of page = footer zone (PR1.2-quality Fix B)
TERM_COL_MARGIN = 30             # points past min_x to still be "term column"
MAX_GLOSSARY_LOOKBACK_PAGES = 30 # how far back to look for the glossary
MIN_TERM_LENGTH = 2
MAX_TERM_LENGTH = 100
MAX_SPLIT_TERM_LENGTH = 50       # max term length when split inline (Term. Def…)
MIN_TERM_WITH_PERIOD = 4         # reject "1." but allow "U.S."
MAX_DEFINITION_LEN = 5000
MAX_FOOTER_LINES_PER_PAGE = 5    # warn when filter is too aggressive (Fix B safety net)

_GLOSSARY_END_PATTERNS = (
    r"^\s*Index\s*(\n|$)",
    r"^\s*References\s*(\n|$)",
    r"^\s*Appendix\s+[A-Z]",
    r"^\s*Bibliography\s*(\n|$)",
)

# PR1.2-quality Fix A: ALL-CAPS heuristic for acronym sections that
# don't preserve bold flags (AR 600-20, FM 6-02, etc).
_ACRONYM_FIRST_WORD_RE = re.compile(r"^[A-Z][A-Z0-9\-]{1,14}$")  # allow digits: AH-64, M-1A1, MC-130
_ACRONYM_LINE_MAX_CHARS = 60       # full-line cap; rules out continuation prose
_ACRONYM_LINE_NO_PERIOD_PREFIX = 30  # no '.' in first N chars


def _looks_like_acronym_term_line(line_text: str) -> bool:
    """True if `line_text` looks like an acronym-list entry rather than a
    continuation. Used as the no-bold fallback for the new-term gate.

    Accepts:
      - First word matches `_ACRONYM_FIRST_WORD_RE` (2-15 chars, upper or
        hyphenated upper)
      - Full line is ≤60 chars
      - No '.' in the first 30 chars (rules out "Furthermore, ..." continuations)
    """
    if not line_text or len(line_text) > _ACRONYM_LINE_MAX_CHARS:
        return False
    if "." in line_text[:_ACRONYM_LINE_NO_PERIOD_PREFIX]:
        return False
    first_word = line_text.split(maxsplit=1)[0] if line_text else ""
    return bool(_ACRONYM_FIRST_WORD_RE.match(first_word))


def _is_term_style_span(span_text: str, span: dict) -> bool:
    """True if a non-leading span looks like part of the term (bold or acronym).
    Used by the multi-span term walk."""
    if text_utils.is_span_bold(span):
        return True
    first_word = span_text.split(maxsplit=1)[0] if span_text else ""
    return bool(_ACRONYM_FIRST_WORD_RE.match(first_word))


def find_glossary_page_range(
    doc: fitz.Document,
    profile: ReferenceProfile,
) -> tuple[int, int] | None:
    """
    Return (start_page_index, end_page_index) inclusive, or None if no
    glossary found. Indices are 0-based (pymupdf native).
    """
    total = len(doc)
    header_res = [
        re.compile(p, re.IGNORECASE | re.MULTILINE)
        for p in profile.glossary_header_patterns
    ]
    end_res = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in _GLOSSARY_END_PATTERNS]

    found_start: int | None = None
    for i in range(total - 1, max(-1, total - MAX_GLOSSARY_LOOKBACK_PAGES - 1), -1):
        page_text = doc[i].get_text("text")
        if any(r.search(page_text) for r in header_res):
            found_start = i
            break
    if found_start is None:
        return None

    end = total - 1
    for i in range(found_start + 1, total):
        page_text = doc[i].get_text("text")
        if any(r.search(page_text) for r in end_res):
            end = i - 1
            break
        # PR1.2-quality Fix D: back-cover detection. UNCLASSIFIED alone is
        # NOT a terminator (appears in many normal-page footers). Require
        # BOTH PIN proximity AND last-3-pages position.
        if _is_back_cover_marker(page_text, i, total):
            end = i - 1
            break
    return (found_start, end)


def _is_back_cover_marker(page_text: str, page_idx: int, total: int) -> bool:
    """True if this page looks like a back-cover / publication-info page,
    not a glossary page. Conservative — requires PIN+position evidence."""
    has_pin = bool(re.search(r"\bPIN\s+\d{4,}", page_text))
    in_last_3 = (total - page_idx) <= 3
    return has_pin and in_last_3


def parse_glossary_entries(
    doc: fitz.Document,
    start: int,
    end: int,
    profile: ReferenceProfile,
) -> list[dict]:
    """
    Walk pages [start, end] inclusive, producing dict entries matching the
    Entry schema (excluding backend-assigned fields like visibility).
    """
    # PR1.2-quality Fix C: case-insensitive so "unclassified" / "section i"
    # / "pin 123" all match regardless of OCR capitalization.
    invalid_res = [re.compile(p, re.IGNORECASE) for p in profile.invalid_term_patterns]
    # PR1.2-quality Fix B: footer-zone-only filter for bare-date / page-num /
    # doc-id+bullet patterns that header_patterns doesn't catch.
    footer_res = [re.compile(p, re.IGNORECASE) for p in profile.footer_patterns]
    citation_pattern = profile.citation_pattern
    header_patterns = profile.header_patterns

    # Term-line split pattern: "Term. Definition…" / "Term — Definition" /
    # "Term  Definition" (multi-space separator). Group 1 = term, 3 = def.
    split_re = re.compile(
        rf"^([A-Za-z0-9\-\.\s/\(\)]{{1,{MAX_SPLIT_TERM_LENGTH}}}?)"
        rf"([\s\.\-—–]{{2,}}|\.\s+|—|–)"
        rf"([A-Z\"\(].*)"
    )

    entries: list[dict] = []

    for page_idx in range(start, end + 1):
        # PR1.2-quality Fix E (Codex iter-3 #9): per-page entries collector
        # so the post-pass continuation merge runs on document-ordered entries
        # from a single page. Then extend the global `entries` list.
        page_entries: list[dict] = []
        try:
            page = doc[page_idx]
        except Exception:
            continue
        page_dict = page.get_text("dict")
        blocks = page_dict.get("blocks", [])
        # PR1.2-quality Fix B: precompute footer-zone Y threshold per page.
        footer_y_threshold = page.rect.height * FOOTER_ZONE_PCT

        # Collect every text span on the page with its Y bucket.
        all_spans: list[dict] = []
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = (span.get("text") or "").strip()
                    if not text:
                        continue
                    all_spans.append(
                        {
                            "bbox": span["bbox"],
                            "text": text,
                            "span": span,
                            "y_round": round(span["bbox"][1], 0),
                        }
                    )

        if not all_spans:
            continue

        # Top-down, then left-right within each Y row.
        all_spans.sort(key=lambda s: (s["y_round"], s["bbox"][0]))

        # Group spans into physical lines by exact rounded Y.
        lines: list[list[dict]] = []
        cur_line: list[dict] = []
        cur_y: float | None = None
        for sp in all_spans:
            if cur_y is None or sp["y_round"] != cur_y:
                if cur_line:
                    lines.append(cur_line)
                cur_line = [sp]
                cur_y = sp["y_round"]
            else:
                cur_line.append(sp)
        if cur_line:
            lines.append(cur_line)

        # Filter document headers + footer-zone noise + invalid lines.
        valid_lines: list[list[dict]] = []
        footer_filtered_count = 0
        for line_spans in lines:
            full_line_text = " ".join(s["text"] for s in line_spans)
            y_pos = line_spans[0]["bbox"][1]
            if (
                y_pos < HEADER_ZONE_Y
                and text_utils.is_document_header(full_line_text, header_patterns)
            ):
                continue
            # PR1.2-quality Fix B: bottom-zone footer filter — bare dates,
            # page nums, doc-id+bullet, "Glossary-N" labels.
            if y_pos > footer_y_threshold and (
                any(r.match(full_line_text) for r in footer_res)
                or text_utils.is_document_header(full_line_text, header_patterns)
            ):
                footer_filtered_count += 1
                continue
            if any(r.match(full_line_text) for r in invalid_res):
                continue
            valid_lines.append(line_spans)
        if footer_filtered_count > MAX_FOOTER_LINES_PER_PAGE:
            # Threshold likely too aggressive; investigate at validation time.
            import warnings
            warnings.warn(
                f"Glossary page {page_idx + 1}: footer filter dropped "
                f"{footer_filtered_count} lines (>{MAX_FOOTER_LINES_PER_PAGE}). "
                f"Possible false-positive footer detection."
            )

        if not valid_lines:
            continue

        # Term column = leftmost X across all valid lines + a tolerance.
        min_x = min(line[0]["bbox"][0] for line in valid_lines)
        term_col_threshold = min_x + TERM_COL_MARGIN

        current_term: str | None = None
        current_def_lines: list[str] = []
        term_page_idx = page_idx  # 0-indexed

        for line_spans in valid_lines:
            first = line_spans[0]
            first_x = first["bbox"][0]
            in_term_col = first_x < term_col_threshold

            # PR1.2-quality Fix A: per-line bold/ALL-CAPS gate.
            # A left-margin line is a NEW term only if its first span is bold
            # OR the line looks acronym-shaped. Otherwise it's a continuation
            # that wraps to the left margin.
            if profile.enable_bold_gate:
                full_line_text = " ".join(s["text"] for s in line_spans).strip()
                is_bold = text_utils.is_span_bold(first["span"])
                is_acronym_line = _looks_like_acronym_term_line(full_line_text)
                is_new_term_line = in_term_col and (is_bold or is_acronym_line)
            else:
                is_new_term_line = in_term_col   # legacy X-only fallback

            if is_new_term_line:
                # PR1.2-quality Fix A multi-span term walk: collect consecutive
                # term-style spans (bold OR acronym-shaped) into the term.
                # Stop on first non-term-style span, terminal-punct + lowercase,
                # or opening-paren citation marker.
                term_spans = [first]
                def_start_idx = len(line_spans)
                for j in range(1, len(line_spans)):
                    sp = line_spans[j]
                    sp_text = sp["text"]
                    if not _is_term_style_span(sp_text, sp["span"]):
                        def_start_idx = j; break
                    if re.search(r"[.!?]\s+[a-z]", sp_text):
                        def_start_idx = j; break
                    if sp_text.startswith("("):
                        def_start_idx = j; break
                    term_spans.append(sp)

                term_text = " ".join(s["text"] for s in term_spans).strip()
                rest_from_def_spans = " ".join(s["text"] for s in line_spans[def_start_idx:])

                # Inline-def split on the joined term_text: "Term. Definition…"
                actual_term = term_text.strip()
                inline_def: str | None = None
                m = split_re.match(term_text)
                if m:
                    t_part = m.group(1).strip()
                    d_part = m.group(3).strip()
                    if len(t_part) < MAX_SPLIT_TERM_LENGTH:
                        actual_term = t_part
                        inline_def = d_part

                # Cleanup: trailing punct + wrapping parens.
                actual_term = actual_term.strip(":,; ")
                if (
                    actual_term.startswith("(")
                    and actual_term.endswith(")")
                    and len(actual_term) > 2
                ):
                    actual_term = actual_term[1:-1].strip()

                # Validation — if any check fails, this is NOT a new term;
                # treat the line as a continuation (or skip if no current
                # term is open). DO NOT flush the previous term.
                if not _validate_term(actual_term, inline_def, invalid_res):
                    if current_term:
                        # Treat the whole line as a continuation.
                        line_text = " ".join(s["text"] for s in line_spans)
                        current_def_lines.append(line_text)
                    continue

                # Flush previous (term, def) before starting new.
                _flush(
                    page_entries,
                    current_term,
                    current_def_lines,
                    term_page_idx,
                    profile,
                    doc,
                    citation_pattern,
                    confidence=0.95,
                    source_type="glossary",
                )

                current_term = actual_term
                current_def_lines = []
                term_page_idx = page_idx
                if inline_def:
                    current_def_lines.append(inline_def)
                # Remaining spans (post-term-walk) become def text.
                if rest_from_def_spans:
                    current_def_lines.append(rest_from_def_spans)
            else:
                # Indented line — definition continuation.
                if current_term is not None:
                    line_text = " ".join(s["text"] for s in line_spans)
                    current_def_lines.append(line_text)

        # End of page — flush whatever's pending.
        _flush(
            page_entries,
            current_term,
            current_def_lines,
            term_page_idx,
            profile,
            doc,
            citation_pattern,
            confidence=0.95,
            source_type="glossary",
        )

        # PR1.2-quality Fix E: per-page continuation merge. Catches residual
        # fragments where Fix A's bold gate didn't cleanly separate a wrapped
        # def line from a real new term (e.g., when the wrapping line happens
        # to start with a bold word that's not actually a term).
        page_entries = _merge_same_page_continuations(page_entries)
        entries.extend(page_entries)

    return entries


def _merge_same_page_continuations(page_entries: list[dict]) -> list[dict]:
    """Merge adjacent same-page entries when the next looks like a
    continuation fragment (lowercase start) of the previous (def doesn't
    end with terminal punctuation). Conservative — only operates on
    document-ordered entries from a single page.
    """
    if len(page_entries) < 2:
        return page_entries
    out = [page_entries[0]]
    for e in page_entries[1:]:
        prev = out[-1]
        prev_def_ends_terminal = bool(re.search(r"[.!?]\s*$", prev.get("definition", "")))
        next_term_starts_lower = bool(re.match(r"^[a-z]", e.get("term", "")))
        if (
            prev["pdf_page_index"] == e["pdf_page_index"]
            and not prev_def_ends_terminal
            and next_term_starts_lower
        ):
            # Merge fragment into prior def
            prev["definition"] = (
                prev.get("definition", "") + " " + e.get("term", "") + " " + e.get("definition", "")
            ).strip()
            continue
        out.append(e)
    return out


def _validate_term(term: str, inline_def: str | None, invalid_res: list[re.Pattern]) -> bool:
    """
    Return True if `term` looks like a valid glossary term.
    Mirrors the OLD source extractor's validation discipline.
    """
    if not term:
        return False

    # Length
    if len(term) > MAX_TERM_LENGTH and not inline_def:
        return False
    if len(term) < MIN_TERM_LENGTH:
        return False

    # Pure number ("1", "1.4", "+1-2")
    if re.match(r"^[\d\.,\+\-]+$", term):
        return False

    # Sentence fragment ending with period — short ones are noise
    if term.endswith(".") and len(term) < MIN_TERM_WITH_PERIOD:
        return False

    # Profile-defined invalid patterns (re-checked after cleanup)
    if any(r.match(term) for r in invalid_res):
        return False

    return True


def _flush(
    entries: list[dict],
    current_term: str | None,
    current_def_lines: list[str],
    page_idx: int,
    profile: ReferenceProfile,
    doc: fitz.Document,
    citation_pattern: str,
    *,
    confidence: float,
    source_type: str,
) -> None:
    """Append the pending entry (if any) to `entries`, applying cleanup + filters."""
    if not current_term or not current_def_lines:
        return
    full_def = " ".join(current_def_lines).strip()
    full_def = text_utils.fix_ocr_spacing(full_def)
    full_def = text_utils.strip_citations(full_def, citation_pattern)
    if not full_def:
        return
    if len(full_def) > MAX_DEFINITION_LEN:
        return
    if text_utils.is_gibberish(full_def):
        return
    entries.append(
        {
            "term": current_term.strip(),
            "term_normalized": normalize_term(current_term),
            "definition": full_def,
            "source_type": source_type,
            "section": "Glossary",
            "pdf_page_index": page_idx + 1,  # convert 0-indexed → 1-indexed
            "printed_page_label": _safe_page_label(doc, page_idx),
            "confidence": confidence,
            "flags": [],
        }
    )


def _safe_page_label(doc: fitz.Document, page_idx: int) -> str | None:
    try:
        label = doc[page_idx].get_label()
    except Exception:
        return None
    return label if label else None
