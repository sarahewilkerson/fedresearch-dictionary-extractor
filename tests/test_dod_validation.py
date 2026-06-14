"""P2-B: DoD corpus validation (real-PDF; @pytest.mark.validation).

Deselected by default (addopts `-m 'not validation'`); run with `-m validation`
after fetching PDFs (scripts/fetch_dod_corpus.py). Covers Codex iter-1 #1
(e2e analyze_pdf: no legacy-gate fallback), per-family entry floors, the
family-matrix required-pass vs experimental split, and manifest sha256
reproducibility (Codex iter-1 #8).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
import yaml

from fedresearch_dictionary_extractor.core.analyzer import analyze_pdf

# A structural-header false positive (NOT "partisan", "particular", etc.).
_HEADER_FP_RE = re.compile(r"^(PART\s+[IVXL0-9]|GLOSSARY|SECTION\b|ABBREVIATIONS\b)", re.I)

REPO = Path(__file__).parent.parent
PDF_DIR = REPO / "validation_set" / "dod_pdfs"
MANIFEST = REPO / "validation_set" / "dod-corpus-manifest.yaml"

pytestmark = pytest.mark.validation

# Per-family minimum-entry floors (required-pass families). Derived from the
# step-7 corpus run; a regression below these signals extraction breakage.
REQUIRED_FLOORS = {
    "DODI_3150.09.pdf": 25,
    "DODM_4140.01.pdf": 40,
    "DoDCPM_1400.25v1471.pdf": 15,
    "AI_31.pdf": 5,
    "DODD_7730.65.pdf": 3,
    "DODI_3305.14.pdf": 3,
    "DTM_13-008.pdf": 3,
}


def _manifest_docs() -> list[dict]:
    return yaml.safe_load(MANIFEST.read_text())["docs"]


def _pdf(local: str) -> Path:
    p = PDF_DIR / local
    if not p.exists():
        pytest.skip(f"PDF not fetched: {p} (run scripts/fetch_dod_corpus.py)")
    return p


@pytest.mark.parametrize("doc", _manifest_docs(), ids=lambda d: d["local"])
def test_manifest_sha256(doc: dict) -> None:
    p = _pdf(doc["local"])
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    assert sha.startswith(doc["sha256_prefix"]), f"{doc['local']} sha256 drift"


@pytest.mark.parametrize("local,floor", REQUIRED_FLOORS.items())
def test_required_family_entry_floor(local: str, floor: int) -> None:
    p = _pdf(local)
    payload = analyze_pdf(str(p), profile_name="dod", deterministic=True)
    entries = payload["entries"]
    assert len(entries) >= floor, f"{local}: {len(entries)} entries < floor {floor}"
    # No structural-header false positives in any required doc.
    for e in entries:
        assert not _HEADER_FP_RE.match(e["term"]), f"{local}: header FP {e['term']!r}"


def test_dodi_3150_09_e2e_no_legacy_fallback() -> None:
    """Codex iter-1 #1: the analyzer legacy-gate fallback must NOT fire for DoD
    (enable_bold_gate=False short-circuits it); otherwise the X-only path would
    over-segment the left-justified block."""
    p = _pdf("DODI_3150.09.pdf")
    payload = analyze_pdf(str(p), profile_name="dod", deterministic=True)
    assert payload["metadata"]["glossary_used_legacy_fallback"] is False
    assert payload["metadata"]["glossary_pages"][:1] == [33]  # 1-indexed PART I start
    terms = [e["term"] for e in payload["entries"]]
    assert "CBR hardness" in terms and "DODIN" in terms
