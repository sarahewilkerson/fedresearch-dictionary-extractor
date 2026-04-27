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
from ..profiles.army import SECTION_AFTER_II_HEADER, SECTION_I_HEADER, SECTION_II_HEADER
from ..profiles.base import ReferenceProfile
from . import text as text_utils

# Section structure label values (Unit 2 of v0.2.0).
# Detection-only — does NOT change extraction behavior. Used by
# core/analyzer.py to emit metadata.section_structure.
SECTION_STRUCTURE_NONE = "none"
SECTION_STRUCTURE_I_ONLY = "section_i_only"
SECTION_STRUCTURE_II_ONLY = "section_ii_only"
SECTION_STRUCTURE_BOTH = "both"
SECTION_STRUCTURE_UNKNOWN = "unknown"  # detection error, no glossary range, or non-Army profile

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

# PR-A v0.3.0 fix #2: Army "changed since previous publication" markers
# (leading `*` and `**`) are stripped from terms; the strip is recorded
# on the entry's flags list under this key.
CHANGED_SINCE_PRIOR_PUB_FLAG = "changed_since_prior_pub"
_LEADING_ASTERISKS_RE = re.compile(r"^\*+\s*")


def _strip_asterisk_prefix(term: str) -> tuple[str, bool]:
    """Strip leading `*` (or `**`, `***`) from `term` and report whether
    a strip occurred. Internal asterisks are preserved, as are bare
    asterisk-only strings (which the validator rejects elsewhere).
    """
    if not term:
        return term, False
    m = _LEADING_ASTERISKS_RE.match(term)
    if not m:
        return term, False
    stripped = term[m.end():]
    if not stripped:
        # Bare `*` / `**` — preserve so the validator (or a caller-side
        # invalid-term filter) sees the original and rejects.
        return term, False
    return stripped, True

_GLOSSARY_END_PATTERNS = (
    r"^\s*Index\s*(\n|$)",
    r"^\s*References\s*(\n|$)",
    r"^\s*Appendix\s+[A-Z]",
    r"^\s*Bibliography\s*(\n|$)",
)

# PR1.2-quality Fix A: ALL-CAPS heuristic for acronym sections that
# don't preserve bold flags (AR 600-20, FM 6-02, etc).
# Codex iter-3 #2 fix: allow dots in the first word so dotted acronyms like
# "U.S.", "U.S.C.", "A.D.", "P.O.W." are correctly recognized as terms.
_ACRONYM_FIRST_WORD_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{1,14}$")  # allow digits + dots
_DOTTED_ACRONYM_RE = re.compile(r"[A-Z]\.[A-Z]")  # interior dot pattern (U.S, P.O.W) — not "III."
_ACRONYM_LINE_MAX_CHARS = 60       # full-line cap; rules out continuation prose
_ACRONYM_LINE_NO_PERIOD_PREFIX = 30  # period-in-first-N filter for non-dotted acronym lines


def _looks_like_acronym_term_line(line_text: str) -> bool:
    """True if `line_text` looks like an acronym-list entry rather than a
    continuation. Used as the no-bold fallback for the new-term gate.

    Accepts:
      - First word matches `_ACRONYM_FIRST_WORD_RE` (2-15 chars, upper /
        digit / dot / hyphen — covers AIT, USINDOPACOM, M-1A1, U.S.,
        U.S.C., AH-64, P.O.W.)
      - Full line is ≤60 chars
      - For first words WITHOUT dots: no period anywhere in the first 30
        chars (rules out wrapped citations like "DODD 6490.02E)" where
        the acronym is followed by a numeric reference). Dotted-acronym
        first words (U.S., U.S.C., etc.) are exempt — the dots are part
        of the acronym, not a sentence boundary. (Codex iter-3 #2 fix +
        rerun regression fix.)
    """
    if not line_text or len(line_text) > _ACRONYM_LINE_MAX_CHARS:
        return False
    first_word = line_text.split(maxsplit=1)[0] if line_text else ""
    if not _ACRONYM_FIRST_WORD_RE.match(first_word):
        return False
    # Conditional period filter: applies UNLESS the first word is a
    # genuine dotted acronym (interior `[A-Z]\.[A-Z]` pattern — U.S.,
    # P.O.W., U.S.C). A trailing-dot-only word like "III." or "MLK." is
    # NOT a dotted acronym and the period filter still applies, so
    # "III. The committee" continuation lines are correctly rejected.
    is_dotted_acronym = bool(_DOTTED_ACRONYM_RE.search(first_word))
    if not is_dotted_acronym and "." in line_text[:_ACRONYM_LINE_NO_PERIOD_PREFIX]:
        return False
    return True


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


def detect_section_structure(
    doc: fitz.Document,
    start: int | None,
    end: int | None,
    profile: ReferenceProfile,
) -> str:
    """Detect Section I/II header presence within the glossary page range.
    Detection only — does NOT change range or extraction behavior (Unit 3 scope).

    Returns one of:
      - "none"             — Army profile, range scanned, no headers found
      - "section_i_only"   — Section I header found, no Section II
      - "section_ii_only"  — Section II header found, no Section I
      - "both"             — both found
      - "unknown"          — non-Army profile, no glossary range, or page-read error

    Profile-gated: only Army-profile docs use these regexes (other profiles
    don't currently have section-structure semantics defined).

    Range coverage caveat: scans only [start, end] from find_glossary_page_range.
    If a Section I header lives on the page BEFORE the glossary header is
    detected, this returns "section_ii_only" or "none" falsely. Unit 3 verifies
    distribution against all 27 candidate-output PDFs and tightens range
    detection if needed.
    """
    if profile.name != "army":
        return SECTION_STRUCTURE_UNKNOWN
    if start is None or end is None:
        # No glossary range available — distinct from "scanned, found nothing".
        return SECTION_STRUCTURE_UNKNOWN
    has_i = False
    has_ii = False
    for page_idx in range(start, end + 1):
        try:
            page_text = doc[page_idx].get_text("text")
        except Exception:
            # Any page-read error → unknown for the whole doc.
            # Simpler/safer than partial-preference: a read error on the
            # page containing the OTHER section's header would otherwise
            # misclassify a "both" doc as single-section.
            return SECTION_STRUCTURE_UNKNOWN
        if not has_ii and SECTION_II_HEADER.search(page_text):
            has_ii = True
        if not has_i and SECTION_I_HEADER.search(page_text):
            has_i = True
        if has_i and has_ii:
            break
    if has_i and has_ii:
        return SECTION_STRUCTURE_BOTH
    if has_ii:
        return SECTION_STRUCTURE_II_ONLY
    if has_i:
        return SECTION_STRUCTURE_I_ONLY
    return SECTION_STRUCTURE_NONE


def narrow_to_section_ii(
    doc: fitz.Document,
    start: int,
    end: int,
) -> dict:
    """When Section II is present in [start, end], return a narrowed range
    plus diagnostics. Caller is responsible for invoking this only when
    section_structure ∈ {"both", "section_ii_only"}; otherwise pass the
    original (start, end) to parse_glossary_entries unchanged.

    Returns a dict with:
      - 'start': new start page (>= original start)
      - 'end': new end page (<= original end)
      - 'fired': True iff narrowing produced a non-empty narrowed range;
                 False on identity transform
      - 'boundary_scan_errors': count of pages that errored during the
                                forward scan for SECTION_AFTER_II_HEADER

    Identity transform (fired=False) cases:
      1. SECTION_II_HEADER doesn't match in [start, end] (caller-gating
         violation OR every Section II page errored on read).
      2. Narrowed range is empty (new_end < new_start).

    Page-read errors during the forward scan for the post-II boundary are
    tolerated (page is skipped) but counted in boundary_scan_errors. The
    caller surfaces the count as metadata.section_ii_boundary_scan_errors
    so distribution analysis can flag scan-error-affected docs for review
    (Codex Unit-3 iter-3 #7).

    Known limitation (Codex Unit-3 iter-3 #6): if Section II header AND the
    next section header occur on the SAME page, narrowing produces an
    empty range → identity transform → preserves current (buggy) behavior
    on that doc shape. Distribution analysis surfaces affected docs via
    fired=False on a 'both'/'section_ii_only' classification. Line-level
    boundary detection deferred to a follow-up unit if the local corpus
    contains such docs.
    """
    found_section_ii_at: int | None = None
    for page_idx in range(start, end + 1):
        try:
            page_text = doc[page_idx].get_text("text")
        except Exception:
            continue
        if SECTION_II_HEADER.search(page_text):
            found_section_ii_at = page_idx
            break

    if found_section_ii_at is None:
        return {
            "start": start,
            "end": end,
            "fired": False,
            "boundary_scan_errors": 0,
        }

    new_start = found_section_ii_at
    new_end = end
    boundary_scan_errors = 0
    for page_idx in range(found_section_ii_at + 1, end + 1):
        try:
            page_text = doc[page_idx].get_text("text")
        except Exception:
            boundary_scan_errors += 1
            continue
        if SECTION_AFTER_II_HEADER.search(page_text):
            new_end = page_idx - 1
            break

    if new_end < new_start:
        # Defense-in-depth: empty range → identity transform.
        return {
            "start": start,
            "end": end,
            "fired": False,
            "boundary_scan_errors": boundary_scan_errors,
        }

    return {
        "start": new_start,
        "end": new_end,
        "fired": True,
        "boundary_scan_errors": boundary_scan_errors,
    }


def _is_back_cover_marker(page_text: str, page_idx: int, total: int) -> bool:
    """True if this page looks like a back-cover / publication-info page,
    not a glossary page. Conservative — requires PIN+position evidence.

    PIN format variants accepted (Codex iter-exec finding #1):
    - "PIN 123456-000" (no colon)
    - "PIN: 123456-000" (with colon — common in formal Army publications)
    - lowercase "pin ..." (OCR variant)
    """
    has_pin = bool(re.search(r"\bPIN\s*:?\s*\d{4,}", page_text, re.IGNORECASE))
    in_last_3 = (total - page_idx) <= 3
    return has_pin and in_last_3


def parse_glossary_entries(
    doc: fitz.Document,
    start: int,
    end: int,
    profile: ReferenceProfile,
    *,
    force_legacy_gate: bool = False,
) -> list[dict]:
    """
    Walk pages [start, end] inclusive, producing dict entries matching the
    Entry schema (excluding backend-assigned fields like visibility).

    If `force_legacy_gate=True`, the per-line bold/ALL-CAPS gate is bypassed
    (X-only). Used internally as a doc-level fallback when the bold-gate
    parse produces zero entries despite ample valid lines (PR1.2-quality
    Fix A safety net for OCR'd PDFs with no preserved bold flags AND
    no ALL-CAPS terms — e.g., GlyphLessFont scans of ADP 3-07).
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
                f"Possible false-positive footer detection.",
                stacklevel=2,
            )

        if not valid_lines:
            continue

        # Term column = leftmost X across all valid lines + a tolerance.
        min_x = min(line[0]["bbox"][0] for line in valid_lines)
        term_col_threshold = min_x + TERM_COL_MARGIN

        current_term: str | None = None
        current_term_flags: list[str] = []
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
            if profile.enable_bold_gate and not force_legacy_gate:
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
                        def_start_idx = j
                        break
                    if re.search(r"[.!?]\s+[a-z]", sp_text):
                        def_start_idx = j
                        break
                    if sp_text.startswith("("):
                        def_start_idx = j
                        break
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

                # PR-A v0.3.0 fix #2: strip Army "changed since previous
                # publication" marker (leading `*` or `**`) and record on
                # the entry's flags so downstream consumers can surface
                # provenance without re-parsing the PDF.
                actual_term, was_changed = _strip_asterisk_prefix(actual_term)
                term_flags = [CHANGED_SINCE_PRIOR_PUB_FLAG] if was_changed else []

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
                    flags=current_term_flags,
                )

                current_term = actual_term
                current_term_flags = term_flags
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
            flags=current_term_flags,
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
    continuation fragment (lowercase start, sentence-fragment-shaped) of
    the previous (def doesn't end with terminal punctuation).

    Conservative — only merges when the "term" is unmistakably a fragment,
    not a real lowercase headword (lowercase real headwords like
    "synchronization", "planning", "spillage" are common in Army doctrine
    glossaries and must NOT be merged).

    Heuristic for "fragment-shaped":
    - Lowercase start AND
    - (≥4 words OR contains sentence-internal punctuation `,;:` OR
      ends with stop-word like "and"/"or"/"the"/etc.)
    """
    if len(page_entries) < 2:
        return page_entries

    stop_tail = {"and", "or", "the", "of", "to", "with", "in", "on", "for",
                 "by", "as", "are", "is", "was", "were", "that", "which", "who"}

    def _looks_like_fragment(term: str) -> bool:
        if not term or not term[0].islower():
            return False
        words = term.split()
        if len(words) >= 4:
            return True
        if re.search(r"[,;:]", term):
            return True
        if words and words[-1].lower().rstrip(".,;:") in stop_tail:
            return True
        return False

    def _ends_terminal(text: str) -> bool:
        # Treat ".)", "?)", "!)", as terminal too — citation parens after a sentence.
        return bool(re.search(r"[.!?][\")\]]?\s*$", text))

    out = [page_entries[0]]
    for e in page_entries[1:]:
        prev = out[-1]
        prev_def_ends_terminal = _ends_terminal(prev.get("definition", ""))
        if (
            prev["pdf_page_index"] == e["pdf_page_index"]
            and not prev_def_ends_terminal
            and _looks_like_fragment(e.get("term", ""))
        ):
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
    flags: list[str] | None = None,
) -> None:
    """Append the pending entry (if any) to `entries`, applying cleanup + filters.

    The optional `flags` parameter is copied (not aliased) onto the emitted
    entry so callers can safely mutate or reuse their list.
    """
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
            "flags": list(flags) if flags else [],
        }
    )


def _safe_page_label(doc: fitz.Document, page_idx: int) -> str | None:
    try:
        label = doc[page_idx].get_label()
    except Exception:
        return None
    return label if label else None
