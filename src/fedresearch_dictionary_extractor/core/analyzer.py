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
) -> dict:
    """Extract definitions from a single PDF and return a schema-v1 payload."""
    pdf_path = Path(pdf_path)
    profile = get_profile(profile_name)

    doc = fitz.open(str(pdf_path))
    try:
        text_layer = text_utils.has_text_layer(doc)
        text_sha = text_utils.compute_text_sha256(doc) if text_layer else None

        glossary_entries: list[dict] = []
        glossary_pages: list[int] = []
        glossary_used_fallback = False
        if text_layer:
            page_range = glossary.find_glossary_page_range(doc, profile)
            if page_range:
                start, end = page_range
                glossary_pages = list(range(start + 1, end + 2))  # 1-indexed for output
                glossary_entries = glossary.parse_glossary_entries(doc, start, end, profile)
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
                    fallback_entries = glossary.parse_glossary_entries(
                        doc, start, end, profile, force_legacy_gate=True
                    )
                    if len(fallback_entries) > len(glossary_entries):
                        glossary_entries = fallback_entries
                        glossary_used_fallback = True

        inline_entries: list[dict] = []
        if text_layer:
            inline_entries = inline.extract_inline_definitions(doc, profile)

        deduped = _dedupe_within_doc(glossary_entries, inline_entries)

        return {
            "schema_version": SCHEMA_VERSION,
            "source_pdf": pdf_path.name,
            "source_gcs_key": gcs_key,
            "source_doc_id": doc_id,
            "source_pub_number": _guess_pub_number(pdf_path.name, profile),
            "source_doc_type": _guess_doc_type(pdf_path.name, profile),
            "extractor_version": __version__,
            "extraction_timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
            },
        }
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
