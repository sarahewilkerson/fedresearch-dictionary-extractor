"""v0.5 D-1: 31-doc validation set golden-output stability.

For each PDF in validation_set/pdfs/, the v0.5 output must match the v0.4
golden output captured at commit c4d1611, UNLESS a deviation is explicitly
listed in v0.5-unit-d1-accepted-deviations.yaml.

Compares:
- detected_range (start, end)
- term_count
- term_set (sorted list of term_normalized)
- section_structure
- section_ii_pages
- section_ii_narrowing_fired
- glossary_used_legacy_fallback

Plan §A4 + §A5: separate deviation file (not inside the golden) prevents
accidentally approving regressions in the same artifact that defines the
baseline.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from fedresearch_dictionary_extractor.core.analyzer import analyze_pdf

REPO = Path(__file__).parent.parent
PDF_DIR = REPO / "validation_set" / "pdfs"
GOLDEN = REPO / "validation_set" / "v0.5-unit-d1-v04-golden-output.json"
DEVIATIONS = REPO / "validation_set" / "v0.5-unit-d1-accepted-deviations.yaml"


def _parse_deviations_yaml() -> dict[str, dict]:
    """Minimal YAML parser for the deviations schema.

    Returns dict {document_id: {old_v04_range, new_v05_range, ...}}.
    Only the top-level fields needed for skip-decision are extracted;
    nested term_set_diff is recorded as text for diagnostics.
    """
    text = DEVIATIONS.read_text()
    if re.search(r"^entries:\s*\[\s*\]\s*$", text, re.MULTILINE):
        return {}
    out: dict[str, dict] = {}
    cur_id: str | None = None
    for line in text.splitlines():
        if line.startswith("  - document_id:"):
            cur_id = line.split(":", 1)[1].strip()
            out[cur_id] = {"raw": []}
        elif cur_id and (line.startswith("    ") or line.startswith("      ")):
            out[cur_id]["raw"].append(line)
    return out


GOLDEN_BY_STEM: dict[str, dict] = json.loads(GOLDEN.read_text())
DEVIATIONS_BY_STEM: dict[str, dict] = _parse_deviations_yaml()


@pytest.mark.parametrize(
    "stem",
    sorted(GOLDEN_BY_STEM.keys()),
    ids=lambda s: s[:40],
)
def test_validation_set_golden_output_stable(stem: str) -> None:
    """For each validation-set PDF, v0.5 output matches the v0.4 golden
    UNLESS listed in accepted-deviations.yaml."""
    if stem in DEVIATIONS_BY_STEM:
        pytest.skip(f"{stem}: explicit accepted deviation — see accepted-deviations.yaml")

    pdf_path = PDF_DIR / f"{stem}.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF not available: {pdf_path}")

    golden = GOLDEN_BY_STEM[stem]
    if "error" in golden:
        pytest.skip(f"{stem}: v0.4 errored (skipping comparison)")

    out = analyze_pdf(str(pdf_path), profile_name="army", deterministic=True)
    md = out["metadata"]

    gp = md.get("glossary_pages") or []
    detected_range = [gp[0] - 1, gp[-1] - 1] if gp else None
    term_set = sorted({e["term_normalized"] for e in out.get("entries", []) if e.get("term_normalized")})

    actual = {
        "detected_range": detected_range,
        "term_count": len(out.get("entries", [])),
        "term_set": term_set,
        "section_structure": md.get("section_structure"),
        "section_ii_pages": md.get("section_ii_pages"),
        "section_ii_narrowing_fired": md.get("section_ii_narrowing_fired"),
        "glossary_used_legacy_fallback": md.get("glossary_used_legacy_fallback"),
    }
    expected = {k: golden.get(k) for k in actual}

    assert actual == expected, (
        f"{stem}: v0.5 output differs from v0.4 golden.\n"
        f"  detected_range: {actual['detected_range']} vs golden {expected['detected_range']}\n"
        f"  term_count: {actual['term_count']} vs golden {expected['term_count']}\n"
        f"  section_structure: {actual['section_structure']} vs golden {expected['section_structure']}\n"
        f"  section_ii_pages: {actual['section_ii_pages']} vs golden {expected['section_ii_pages']}\n"
        f"  term_set_diff added: {sorted(set(actual['term_set']) - set(expected['term_set']))[:10]}\n"
        f"  term_set_diff removed: {sorted(set(expected['term_set']) - set(actual['term_set']))[:10]}\n"
        f"Add an entry to validation_set/v0.5-unit-d1-accepted-deviations.yaml "
        f"if this deviation is intentional."
    )
