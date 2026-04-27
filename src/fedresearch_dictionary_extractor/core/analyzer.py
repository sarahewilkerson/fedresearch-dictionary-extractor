"""
Top-level orchestrator. Opens a PDF, runs glossary + inline extractors,
dedupes, and returns a payload matching schema v1.
"""
from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path

import fitz

from .. import SCHEMA_VERSION, __version__
from ..extractors import glossary, inline
from ..extractors import text as text_utils
from ..profiles import get_profile
from ..profiles.base import ReferenceProfile


def analyze_pdf(
    pdf_path: str | Path,
    *,
    profile_name: str = "army",
    gcs_key: str | None = None,
    doc_id: str | None = None,
    deterministic: bool = False,
) -> dict:
    """Extract definitions from a single PDF and return a schema-v1 payload.

    When ``deterministic=True`` (PR-A v0.3.0 fix #5), wall-clock-derived
    fields are omitted from the output so two runs against the same input
    produce byte-identical JSON. Currently this means ``extraction_timestamp``
    is suppressed; it is the only such field today, but the gate is here
    so future additions stay in one place.
    """
    pdf_path = Path(pdf_path)
    profile = get_profile(profile_name)

    doc = fitz.open(str(pdf_path))
    try:
        text_layer = text_utils.has_text_layer(doc)
        text_sha = text_utils.compute_text_sha256(doc) if text_layer else None

        glossary_entries: list[dict] = []
        glossary_pages: list[int] = []
        glossary_used_fallback = False
        section_structure = glossary.SECTION_STRUCTURE_UNKNOWN
        # Unit 3: Section II range scoping.
        section_ii_pages: list[int] | None = None
        section_ii_narrowing_attempted = False
        section_ii_narrowing_fired = False
        section_ii_boundary_scan_errors = 0
        if text_layer:
            page_range = glossary.find_glossary_page_range(doc, profile)
            if page_range:
                start, end = page_range
                glossary_pages = list(range(start + 1, end + 2))  # 1-indexed for output
                section_structure = glossary.detect_section_structure(
                    doc, start, end, profile
                )
                # Unit 3: narrow range when Section II is detected.
                parse_start, parse_end = start, end
                if section_structure in (
                    glossary.SECTION_STRUCTURE_BOTH,
                    glossary.SECTION_STRUCTURE_II_ONLY,
                ):
                    section_ii_narrowing_attempted = True
                    narrow = glossary.narrow_to_section_ii(doc, start, end)
                    parse_start = narrow["start"]
                    parse_end = narrow["end"]
                    section_ii_narrowing_fired = narrow["fired"]
                    section_ii_boundary_scan_errors = narrow["boundary_scan_errors"]
                    if section_ii_narrowing_fired:
                        section_ii_pages = list(
                            range(parse_start + 1, parse_end + 2)
                        )
                # PR-A v0.3.0 fix #3: pass the Section II header pattern into
                # parse_glossary_entries so the first page's Section I tail
                # (when present) gets clipped before per-line parsing.
                section_ii_pattern = (
                    glossary.SECTION_II_HEADER if section_ii_narrowing_fired else None
                )
                glossary_entries = glossary.parse_glossary_entries(
                    doc,
                    parse_start,
                    parse_end,
                    profile,
                    section_ii_header_pattern=section_ii_pattern,
                )
                # PR1.2-quality Fix A safety net: doc-level fallback when bold
                # flags are essentially ABSENT in the glossary section
                # (GlyphLessFont OCR'd PDFs). Catches ADP 3-07 + FM 3-34 type
                # cases where bold detection gives 0/very few entries because
                # there are no bold spans to detect.
                #
                # Codex iter-3 #1 fix: the prior threshold (entries < page_count)
                # over-fired on docs with sparse-but-correct bold output (a
                # 3-entry glossary spanning 5 pages would falsely fall back).
                # New trigger: measure actual bold-flag preservation rate on
                # the glossary section. Below 10% means the PDF has functionally
                # lost bold metadata (real Army doc bold rates are 20-50% on
                # glossary pages with proper formatting). Threshold tuned
                # empirically: ADP 3-07=0%, FM 3-34=3%, AR 600-20=24%,
                # AR 135-100=21%. 10% catches the 0-3% cases while leaving
                # the 20%+ cases on the bold path.
                if (
                    profile.enable_bold_gate
                    and _bold_preservation_rate(doc, start, end) < 0.10
                ):
                    # Unit 3: bold-fallback path also uses the narrowed range
                    # so Section II content is preserved on the fallback.
                    # Bold-rate trigger uses the FULL range (more samples =
                    # more reliable signal); only the parse uses narrowed.
                    fallback_entries = glossary.parse_glossary_entries(
                        doc,
                        parse_start,
                        parse_end,
                        profile,
                        force_legacy_gate=True,
                        section_ii_header_pattern=section_ii_pattern,
                    )
                    if len(fallback_entries) > len(glossary_entries):
                        glossary_entries = fallback_entries
                        glossary_used_fallback = True

        inline_entries: list[dict] = []
        if text_layer:
            inline_entries = inline.extract_inline_definitions(doc, profile)

        deduped = _dedupe_within_doc(glossary_entries, inline_entries)

        payload: dict = {
            "schema_version": SCHEMA_VERSION,
            "source_pdf": pdf_path.name,
            "source_gcs_key": gcs_key,
            "source_doc_id": doc_id,
            "source_pub_number": _guess_pub_number(pdf_path.name, profile),
            "source_doc_type": _guess_doc_type(pdf_path.name, profile),
            "extractor_version": __version__,
            "profile": profile.name,
            "text_sha256": text_sha,
            "entries": deduped,
            "metadata": {
                "total_pages": len(doc),
                "glossary_pages": glossary_pages,
                "text_layer_present": text_layer,
                "entries_glossary": len(glossary_entries),
                "entries_inline": len(inline_entries),
                "entries_after_dedup": len(deduped),
                # PR1.2-quality Codex iter-3 #7: diagnostics for the bold
                # gate fallback. True iff parse_glossary_entries was retried
                # with X-only mode after the bold-gated run produced zero.
                "glossary_used_legacy_fallback": glossary_used_fallback,
                # Unit 2 of v0.2.0: detection-only Section I/II structure label.
                # See extractors/glossary.detect_section_structure for semantics.
                "section_structure": section_structure,
                # Unit 3: Section II range scoping diagnostics.
                # section_ii_pages: 1-based narrowed page range (or null if
                # narrowing didn't fire).
                "section_ii_pages": section_ii_pages,
                # narrowing_attempted: did we try narrowing? True only when
                # section_structure ∈ {both, section_ii_only}.
                "section_ii_narrowing_attempted": section_ii_narrowing_attempted,
                # narrowing_fired: did narrowing succeed? attempted=True +
                # fired=False = identity-fallback (preserves prior behavior;
                # distribution analysis flags for review).
                "section_ii_narrowing_fired": section_ii_narrowing_fired,
                # boundary_scan_errors: count of pages that errored during
                # the forward scan for the post-II section header. > 0 means
                # range may extend past Section II — flag for review.
                "section_ii_boundary_scan_errors": section_ii_boundary_scan_errors,
            },
        }
        # PR-A v0.3.0 fix #5: emit extraction_timestamp only when caller
        # accepts non-deterministic output. Schema's required list no
        # longer includes this field (schema v1, additive removal).
        if not deterministic:
            payload["extraction_timestamp"] = datetime.now(UTC).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        return payload
    finally:
        doc.close()


def _bold_preservation_rate(doc: fitz.Document, start: int, end: int) -> float:
    """Fraction of first-spans across the glossary range that are bold.

    Used (Codex iter-3 #1 fix) to detect docs that have lost bold metadata
    (typically OCR'd PDFs using GlyphLessFont). When this is essentially
    zero, the bold-gate parse will mis-classify everything as continuation
    and the legacy X-only fallback should fire.

    Threshold for fallback decision is set by the caller (currently 1%);
    this helper only computes the metric.
    """
    bold_count = 0
    total = 0
    for page_idx in range(start, end + 1):
        try:
            page = doc[page_idx]
        except Exception:
            continue
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                spans = [s for s in line.get("spans", []) if (s.get("text") or "").strip()]
                if not spans:
                    continue
                first = spans[0]
                total += 1
                if text_utils.is_span_bold(first):
                    bold_count += 1
    return bold_count / total if total else 0.0


def _dedupe_within_doc(glossary_entries: list[dict], inline_entries: list[dict]) -> list[dict]:
    """
    Same `term_normalized` from same PDF: prefer glossary; tiebreak higher
    confidence; tiebreak lower pdf_page_index.

    Per the parent plan §3.1: "DB doesn't silently drop duplicates" — the
    extractor dedupes at emit time so the unique constraint
    `(documentId, termNormalized, sourceType, pdfPageIndex)` doesn't
    constraint-violate on legitimate intra-doc collisions.
    """

    def _key(e: dict) -> str:
        return e["term_normalized"]

    def _rank(e: dict) -> tuple[int, float, int]:
        # lower is better
        src_priority = 0 if e["source_type"] == "glossary" else 1
        confidence_neg = -(e.get("confidence") or 0.0)
        page = e["pdf_page_index"]
        return (src_priority, confidence_neg, page)

    by_term: dict[str, dict] = {}
    for entry in [*glossary_entries, *inline_entries]:
        if not entry["term_normalized"]:
            continue
        key = _key(entry)
        existing = by_term.get(key)
        if existing is None or _rank(entry) < _rank(existing):
            by_term[key] = entry
    return list(by_term.values())


def _guess_pub_number(filename: str, profile: ReferenceProfile) -> str | None:
    base = os.path.splitext(filename)[0].replace("_", " ").replace("-", "-")
    for pattern, prefix in profile.publication_patterns:
        m = re.search(pattern, base, re.IGNORECASE)
        if m:
            number = m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)
            return f"{prefix} {number}"
    return None


def _guess_doc_type(filename: str, profile: ReferenceProfile) -> str | None:
    pub = _guess_pub_number(filename, profile)
    if not pub:
        return None
    return pub.split()[0]
