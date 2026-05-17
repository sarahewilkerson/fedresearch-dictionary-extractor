"""v0.5 Unit 0 diagnostic — characterize the 45 residual zero-entry-with-glossary docs.

Per docs/plans/2026-05-18-v0.5-roadmap-definition-extraction.md § Unit 0:
- Auto-detects "known" glossary range via permissive heuristic on PDF text
  (deviation from plan's "manual" labeling — more reproducible, auditable;
  caller should spot-check a random sample of detected ranges vs the actual
  PDFs to catch heuristic failures).
- Runs 9 measurements per doc.
- Emits a TSV measurement table sorted by document_id.

Inputs:
  --cohort-csv PATH       CSV with header `document_id,canonical_id,gcs_key`
  --pdf-dir PATH          dir containing downloaded PDFs (basename matches gcs_key tail)
  --extracted-text-dir PATH  dir containing per-doc extracted_text dumps (filename: <document_id>.txt)
  --out PATH              output TSV (default: stdout)

Reproducibility: deterministic output for a fixed cohort + corpus snapshot.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import fitz  # pymupdf

# ── Permissive glossary range detection ───────────────────────────────────

# Loose pattern: matches "Glossary" / "GLOSSARY" / "Glossary of Terms" / etc.
# anywhere in a line, not anchored to ^...$ like v0.4's strict regex.
GLOSSARY_HEADER_LOOSE = re.compile(
    r"(?:^|\n)\s*(glossary|GLOSSARY)(\s+of\s+(?:terms?|acronyms?|abbreviations?))?\s*(?:\n|$)",
    re.IGNORECASE,
)
GLOSSARY_END_LOOSE = re.compile(
    r"(?:^|\n)\s*(index|references|bibliography|appendix\s+[A-Z]|PIN\s*:?\s*\d{4,})\b",
    re.IGNORECASE,
)


def detect_known_glossary_range(doc: fitz.Document) -> tuple[int, int] | None:
    """Permissive glossary-range detection used for measurement only.

    Returns (start_page_0idx, end_page_0idx) inclusive, or None.

    Searches the full doc forward (NOT backward like v0.4's strict matcher)
    so docs with glossaries deep in long documents are found regardless of
    lookback distance. Returns the FIRST page matching the loose header.
    End is the page before the next end-section marker, or last page.
    """
    total = len(doc)
    found_start: int | None = None
    for i in range(total):
        try:
            text = doc[i].get_text("text")
        except Exception:
            continue
        # Skip TOC-style matches (line followed by dot-leaders + page number).
        # Heuristic: if "glossary" appears AND the line contains "..." or
        # ends with a digit-only token within ~30 chars after the word,
        # treat as TOC reference and skip.
        m = GLOSSARY_HEADER_LOOSE.search(text)
        if not m:
            continue
        match_start = m.start()
        match_end = m.end()
        post = text[match_end : match_end + 80]
        # Skip if next ~80 chars look like TOC dot-leaders or page numbers
        # AND the page also has many other dot-leader lines (a strong TOC signal).
        page_dot_leader_count = len(re.findall(r"\.{4,}", text))
        if ("…" in post or "...." in post or re.match(r"\s*\d+\s*$", post.split("\n")[0])) and page_dot_leader_count >= 5:
            continue
        found_start = i
        break
    if found_start is None:
        return None

    end = total - 1
    for i in range(found_start + 1, total):
        try:
            text = doc[i].get_text("text")
        except Exception:
            continue
        if GLOSSARY_END_LOOSE.search(text):
            end = i - 1
            break
    if end < found_start:
        end = found_start
    return (found_start, end)


def detected_v04_glossary_range(doc: fitz.Document) -> tuple[int, int] | None:
    """What v0.4's actual find_glossary_page_range returns. Used to record
    the 'detected' label vs the loose 'known' label. We import the live
    extractor to ensure we're measuring the production v0.4 behavior."""
    try:
        from fedresearch_dictionary_extractor.extractors.glossary import find_glossary_page_range
        from fedresearch_dictionary_extractor.profiles import get_profile
    except ImportError:
        return None
    profile = get_profile("army")
    return find_glossary_page_range(doc, profile)


# ── Measurements ──────────────────────────────────────────────────────────

@dataclass
class Measurements:
    document_id: str
    canonical_id: str
    total_pages: int
    known_range_start: int | None   # 0-idx
    known_range_end: int | None
    detected_range_start: int | None   # what v0.4 returns
    detected_range_end: int | None
    range_match: str                 # exact / overlap / different / detected_none / known_none
    # 1. PDF vowel ratio on known-range pages
    pdf_vowel_ratio: float
    # 2. extracted_text vowel ratio over known-range slice (or full text if range not mappable)
    text_vowel_ratio: float
    # 3. control-byte rate in both sources
    pdf_control_byte_rate: float
    text_control_byte_rate: float
    # 4. page-boundary preservation in extracted_text
    text_page_boundaries_detected: bool
    text_page_boundaries_count: int
    # 5. glossary-header detectable from extracted_text alone
    text_glossary_header_detected: bool
    # 6. whitespace+newline preservation in text
    text_newlines_per_char: float
    text_space_run_max: int          # longest run of consecutive spaces (collapsed-OCR signal)
    # 7. Unicode replacement-character rate in text
    text_replacement_char_rate: float
    # 8. reading-order sanity: sentences/char ratio
    text_sentences_per_kchar: float
    # 9. (separate hand-tag pass, not in script)
    notes: str = ""


CONTROL_BYTE_RE = re.compile(r"[\x00-\x08\x0b\x0e-\x1f]")  # excludes \t \n \r \x0c
REPLACEMENT_CHAR = "�"
SENTENCE_END_RE = re.compile(r"[.!?][\s\n]")


def vowel_ratio(text: str) -> float:
    alpha = [c for c in text if c.isalpha()]
    if len(alpha) < 100:
        return 0.0
    vowels = sum(1 for c in alpha if c.lower() in "aeiou")
    return vowels / len(alpha)


def control_byte_rate(text: str) -> float:
    if not text:
        return 0.0
    return len(CONTROL_BYTE_RE.findall(text)) / len(text)


def replacement_char_rate(text: str) -> float:
    if not text:
        return 0.0
    return text.count(REPLACEMENT_CHAR) / len(text)


def newlines_per_char(text: str) -> float:
    if not text:
        return 0.0
    return text.count("\n") / len(text)


def longest_space_run(text: str) -> int:
    """Catches collapsed OCR where words run together (very few or no spaces)
    OR over-padded OCR where many spaces are inserted."""
    if not text:
        return 0
    return max((len(m) for m in re.findall(r" +", text)), default=0)


def sentences_per_kchar(text: str) -> float:
    if not text:
        return 0.0
    sentences = len(SENTENCE_END_RE.findall(text))
    return sentences * 1000 / len(text)


def page_boundary_signals(text: str) -> tuple[bool, int]:
    """Detect page boundaries in extracted_text.

    Look for the FedResearch upstream OCR-pipeline's page delimiter format
    `-- N of M --` first; fall back to FormFeed (`\x0c`).
    """
    n_of_m = len(re.findall(r"--\s*\d+\s+of\s+\d+\s*--", text))
    form_feeds = text.count("\x0c")
    total = max(n_of_m, form_feeds)
    return (total > 0, total)


def slice_text_to_range(text: str, start_page_1idx: int, end_page_1idx: int) -> str:
    """Slice extracted_text to a page range using `-- N of M --` markers.

    If markers aren't present, returns full text. Page indices are 1-based.
    """
    pattern = re.compile(r"--\s*(\d+)\s+of\s+\d+\s*--", re.IGNORECASE)
    matches = list(pattern.finditer(text))
    if not matches:
        return text
    start_idx = None
    end_idx = len(text)
    for m in matches:
        n = int(m.group(1))
        if n == start_page_1idx and start_idx is None:
            start_idx = m.start()
        if n > end_page_1idx:
            end_idx = m.start()
            break
    if start_idx is None:
        return text
    return text[start_idx:end_idx]


def glossary_header_detectable_in_text(text: str) -> bool:
    return bool(GLOSSARY_HEADER_LOOSE.search(text))


# ── Per-doc measurement ───────────────────────────────────────────────────

def measure_doc(
    document_id: str,
    canonical_id: str,
    pdf_path: Path,
    extracted_text_path: Path | None,
) -> Measurements:
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        return Measurements(
            document_id=document_id,
            canonical_id=canonical_id,
            total_pages=0,
            known_range_start=None, known_range_end=None,
            detected_range_start=None, detected_range_end=None,
            range_match="pdf_open_error",
            pdf_vowel_ratio=0.0, text_vowel_ratio=0.0,
            pdf_control_byte_rate=0.0, text_control_byte_rate=0.0,
            text_page_boundaries_detected=False, text_page_boundaries_count=0,
            text_glossary_header_detected=False,
            text_newlines_per_char=0.0, text_space_run_max=0,
            text_replacement_char_rate=0.0, text_sentences_per_kchar=0.0,
            notes=f"pdf_open_error: {exc!s}",
        )
    try:
        total_pages = len(doc)
        known = detect_known_glossary_range(doc)
        detected = detected_v04_glossary_range(doc)

        if known is None and detected is None:
            range_match = "neither"
        elif known is None:
            range_match = "known_none_detected_some"
        elif detected is None:
            range_match = "known_some_detected_none"
        else:
            ks, ke = known
            ds, de = detected
            if (ks, ke) == (ds, de):
                range_match = "exact"
            elif ks <= de and ds <= ke:
                range_match = "overlap"
            else:
                range_match = "disjoint"

        # PDF-source measurements over known range
        if known is not None:
            ks, ke = known
            pdf_text_parts = []
            for i in range(ks, min(ke + 1, total_pages)):
                try:
                    pdf_text_parts.append(doc[i].get_text("text"))
                except Exception:
                    pass
            pdf_text = "\n".join(pdf_text_parts)
        else:
            # fallback: mid-doc page
            mid = total_pages // 2
            try:
                pdf_text = doc[mid].get_text("text")
            except Exception:
                pdf_text = ""

        # Upstream-text measurements
        extracted_text = ""
        if extracted_text_path and extracted_text_path.exists():
            extracted_text = extracted_text_path.read_text(errors="replace")
        if known is not None and extracted_text:
            text_slice = slice_text_to_range(extracted_text, known[0] + 1, known[1] + 1)
        else:
            text_slice = extracted_text

        pb_detected, pb_count = page_boundary_signals(extracted_text)
        gh_detected = glossary_header_detectable_in_text(extracted_text)

        return Measurements(
            document_id=document_id,
            canonical_id=canonical_id,
            total_pages=total_pages,
            known_range_start=known[0] if known else None,
            known_range_end=known[1] if known else None,
            detected_range_start=detected[0] if detected else None,
            detected_range_end=detected[1] if detected else None,
            range_match=range_match,
            pdf_vowel_ratio=round(vowel_ratio(pdf_text), 4),
            text_vowel_ratio=round(vowel_ratio(text_slice), 4),
            pdf_control_byte_rate=round(control_byte_rate(pdf_text), 6),
            text_control_byte_rate=round(control_byte_rate(text_slice), 6),
            text_page_boundaries_detected=pb_detected,
            text_page_boundaries_count=pb_count,
            text_glossary_header_detected=gh_detected,
            text_newlines_per_char=round(newlines_per_char(text_slice), 4),
            text_space_run_max=longest_space_run(text_slice),
            text_replacement_char_rate=round(replacement_char_rate(text_slice), 6),
            text_sentences_per_kchar=round(sentences_per_kchar(text_slice), 2),
        )
    finally:
        doc.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort-csv", required=True, type=Path)
    ap.add_argument("--pdf-dir", required=True, type=Path)
    ap.add_argument("--extracted-text-dir", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    rows: list[Measurements] = []
    with args.cohort_csv.open() as f:
        reader = csv.DictReader(f)
        for row in sorted(reader, key=lambda r: r["document_id"]):
            doc_id = row["document_id"]
            canonical = row["canonical_id"]
            gcs_key = row["gcs_key"]
            pdf_basename = Path(gcs_key).name
            pdf_path = args.pdf_dir / pdf_basename
            text_path = args.extracted_text_dir / f"{doc_id}.txt"
            if not pdf_path.exists():
                rows.append(Measurements(
                    document_id=doc_id, canonical_id=canonical, total_pages=0,
                    known_range_start=None, known_range_end=None,
                    detected_range_start=None, detected_range_end=None,
                    range_match="pdf_missing",
                    pdf_vowel_ratio=0.0, text_vowel_ratio=0.0,
                    pdf_control_byte_rate=0.0, text_control_byte_rate=0.0,
                    text_page_boundaries_detected=False, text_page_boundaries_count=0,
                    text_glossary_header_detected=False,
                    text_newlines_per_char=0.0, text_space_run_max=0,
                    text_replacement_char_rate=0.0, text_sentences_per_kchar=0.0,
                    notes="pdf_missing",
                ))
                continue
            m = measure_doc(doc_id, canonical, pdf_path, text_path)
            rows.append(m)
            print(f"measured {doc_id} ({canonical[:50]})", file=sys.stderr)

    fieldnames = list(asdict(rows[0]).keys()) if rows else []
    out_stream = args.out.open("w") if args.out else sys.stdout
    writer = csv.DictWriter(out_stream, fieldnames=fieldnames, delimiter="\t")
    writer.writeheader()
    for r in rows:
        writer.writerow(asdict(r))
    if args.out:
        out_stream.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
