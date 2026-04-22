"""
Tests for intra-doc dedup logic (analyzer._dedupe_within_doc).

Per the parent plan §3.1: when glossary + inline extract the same
term_normalized from the same PDF, prefer glossary; tiebreak higher
confidence; tiebreak lower pdf_page_index.
"""
from fedresearch_dictionary_extractor.core.analyzer import _dedupe_within_doc


def _entry(term: str, source: str, page: int, conf: float = 0.9) -> dict:
    return {
        "term": term,
        "term_normalized": term.lower(),
        "definition": f"def of {term}",
        "source_type": source,
        "section": None,
        "pdf_page_index": page,
        "printed_page_label": None,
        "confidence": conf,
        "flags": [],
    }


def test_glossary_beats_inline_for_same_term() -> None:
    glossary = [_entry("Commander", "glossary", page=120, conf=0.95)]
    inline = [_entry("Commander", "inline", page=15, conf=0.65)]
    out = _dedupe_within_doc(glossary, inline)
    assert len(out) == 1
    assert out[0]["source_type"] == "glossary"
    assert out[0]["pdf_page_index"] == 120


def test_higher_confidence_wins_within_same_source() -> None:
    a = _entry("Commander", "inline", page=10, conf=0.6)
    b = _entry("Commander", "inline", page=20, conf=0.7)
    out = _dedupe_within_doc([], [a, b])
    assert len(out) == 1
    assert out[0]["confidence"] == 0.7


def test_lower_page_wins_when_source_and_confidence_tie() -> None:
    a = _entry("Commander", "glossary", page=200, conf=0.95)
    b = _entry("Commander", "glossary", page=100, conf=0.95)
    out = _dedupe_within_doc([a, b], [])
    assert len(out) == 1
    assert out[0]["pdf_page_index"] == 100


def test_distinct_terms_all_kept() -> None:
    a = _entry("Commander", "glossary", page=10)
    b = _entry("Officer", "glossary", page=11)
    c = _entry("Recruit", "inline", page=12)
    out = _dedupe_within_doc([a, b], [c])
    assert {e["term_normalized"] for e in out} == {"commander", "officer", "recruit"}


def test_empty_normalized_term_is_dropped() -> None:
    a = _entry("", "glossary", page=10)
    a["term_normalized"] = ""
    out = _dedupe_within_doc([a], [])
    assert out == []
