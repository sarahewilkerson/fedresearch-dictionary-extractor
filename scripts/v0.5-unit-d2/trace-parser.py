"""v0.5 Unit D-2: parser trace script.

For one doc, runs `parse_glossary_entries` with helper-call instrumentation
to record per-line decisions. Output: a per-doc trace file with each line's
verdict.

Trace contract (per D-2 plan H1):
- line_idx, page, leftmost_x, line_text (first 80 chars)
- first_span_bold, is_acronym_line, in_term_col, is_new_term_line
- if new_term: term_after_walk, validation_result, validation_reason
- if continuation: appended to current_def_lines (yes/no — yes if current_term exists)
- flush events: term, def_lines_count, flush_result (emitted | dropped_gibberish | dropped_empty_def | dropped_length)

Mechanism: Option A — mock.patch wraps the helpers (_validate_term,
_looks_like_acronym_term_line, _is_term_style_span, _flush,
_filter_spans_to_below_header). Patches call through to the actual
implementation and append the (args, return) to a thread-local trace.

Inline decisions (in_term_col, is_new_term_line, current_term) are
reconstructed from the helper-call ordering using the parser's known
sequence (validate before flush, etc.).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).parent.parent.parent
COHORT_CSV = REPO_ROOT / "validation_set" / "v0.5-unit-d2-cohort.csv"
RANGE_CSV = REPO_ROOT / "validation_set" / "v0.5-unit-d2-range-validation.csv"
PDF_DIR = Path("/tmp/v05-unit0/pdfs")


def _skip_comments(path: Path):
    text = path.read_text()
    return io.StringIO("\n".join(line for line in text.splitlines() if not line.startswith("#")))


def trace_one(doc_id: str, pdf_path: Path, out_dir: Path) -> dict:
    """Run instrumented parse on one PDF; emit a JSON trace summary.

    Returns a summary dict with counts + first ~20 events.
    """
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from fedresearch_dictionary_extractor.core.analyzer import analyze_pdf
    from fedresearch_dictionary_extractor.extractors import glossary as gmod

    events: list[dict] = []

    # Capture originals
    orig_validate = gmod._validate_term
    orig_acronym = gmod._looks_like_acronym_term_line
    orig_term_style = gmod._is_term_style_span
    orig_flush = gmod._flush
    orig_filter = gmod._filter_spans_to_below_header

    def t_validate(term, inline_def, invalid_res):
        result = orig_validate(term, inline_def, invalid_res)
        events.append({
            "kind": "validate_term",
            "term": term[:80] if term else None,
            "inline_def": (inline_def[:60] if inline_def else None),
            "result": result,
        })
        return result

    def t_acronym(line_text):
        result = orig_acronym(line_text)
        events.append({
            "kind": "looks_like_acronym",
            "line_text": line_text[:80],
            "result": result,
        })
        return result

    def t_term_style(span_text, span):
        result = orig_term_style(span_text, span)
        events.append({
            "kind": "is_term_style_span",
            "span_text": span_text[:60],
            "is_bold": bool(span.get("flags", 0) & 16),
            "result": result,
        })
        return result

    def t_flush(entries, current_term, current_def_lines, page_idx, profile, doc,
                citation_pattern, *, confidence, source_type, flags=None):
        n_def_lines = len(current_def_lines) if current_def_lines else 0
        def_preview = " ".join(current_def_lines)[:100] if current_def_lines else None
        n_entries_before = len(entries)
        orig_flush(entries, current_term, current_def_lines, page_idx, profile, doc,
                   citation_pattern, confidence=confidence, source_type=source_type, flags=flags)
        n_entries_after = len(entries)
        events.append({
            "kind": "flush",
            "term": current_term[:80] if current_term else None,
            "def_lines_count": n_def_lines,
            "def_preview": def_preview,
            "page_idx": page_idx,
            "result": "emitted" if n_entries_after > n_entries_before else "dropped",
        })

    def t_filter(spans, header_pattern):
        result = orig_filter(spans, header_pattern)
        events.append({
            "kind": "filter_spans_below_header",
            "input_count": len(spans),
            "output_count": len(result),
        })
        return result

    with (
        patch.object(gmod, "_validate_term", side_effect=t_validate),
        patch.object(gmod, "_looks_like_acronym_term_line", side_effect=t_acronym),
        patch.object(gmod, "_is_term_style_span", side_effect=t_term_style),
        patch.object(gmod, "_flush", side_effect=t_flush),
        patch.object(gmod, "_filter_spans_to_below_header", side_effect=t_filter),
    ):
        out = analyze_pdf(str(pdf_path), profile_name="army", deterministic=True)

    # Summary
    from collections import Counter
    by_kind = Counter(e["kind"] for e in events)
    validates = [e for e in events if e["kind"] == "validate_term"]
    validate_passed = sum(1 for e in validates if e["result"])
    validate_failed = sum(1 for e in validates if not e["result"])
    flushes = [e for e in events if e["kind"] == "flush"]
    flush_emitted = sum(1 for e in flushes if e["result"] == "emitted")
    flush_dropped = sum(1 for e in flushes if e["result"] == "dropped")

    summary = {
        "document_id": doc_id,
        "entry_count": len(out.get("entries", [])),
        "metadata": {
            "section_structure": out["metadata"].get("section_structure"),
            "section_ii_pages": out["metadata"].get("section_ii_pages"),
            "section_ii_narrowing_fired": out["metadata"].get("section_ii_narrowing_fired"),
            "glossary_used_legacy_fallback": out["metadata"].get("glossary_used_legacy_fallback"),
            "glossary_pages": out["metadata"].get("glossary_pages"),
        },
        "event_counts": dict(by_kind),
        "validate_summary": {"passed": validate_passed, "failed": validate_failed},
        "flush_summary": {"emitted": flush_emitted, "dropped": flush_dropped},
        "sample_events": events[:30],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{doc_id}.json"
    out_file.write_text(json.dumps(summary, indent=2) + "\n")

    # Also write raw events to /tmp (not committed)
    raw_dir = Path("/tmp/d2-traces")
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{doc_id}.json").write_text(json.dumps(events, indent=2) + "\n")

    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT / "validation_set" / "v0.5-unit-d2-trace-summaries")
    args = ap.parse_args()

    # Verified cohort
    verified_ids = []
    for r in csv.DictReader(_skip_comments(RANGE_CSV)):
        if r["range_correct"] == "true":
            verified_ids.append(r["document_id"])
    cohort = {r["document_id"]: r for r in csv.DictReader(_skip_comments(COHORT_CSV))}

    for doc_id in sorted(verified_ids):
        pdf_path = PDF_DIR / Path(cohort[doc_id]["gcs_key"]).name
        print(f"tracing {doc_id[:16]}...", file=sys.stderr)
        s = trace_one(doc_id, pdf_path, args.out_dir)
        print(f"  events={sum(s['event_counts'].values())}  validate_pass={s['validate_summary']['passed']}/{s['validate_summary']['passed']+s['validate_summary']['failed']}  flush_emit={s['flush_summary']['emitted']}/{s['flush_summary']['emitted']+s['flush_summary']['dropped']}  entries={s['entry_count']}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
