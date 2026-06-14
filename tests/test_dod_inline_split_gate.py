"""P2-B: inline_split term-gate behavior (synthetic, PDF-free).

DoD definition pages are left-justified (term + continuation at the same x)
and OCR'd (no bold), so the only reliable new-term discriminator is textual:
a line matching `^Term.  <Capital>` (the split pattern). These tests pin that
behavior on parse_glossary_entries when the profile sets
term_gate_mode="inline_split". RED until the branch + base.py properties land.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from fedresearch_dictionary_extractor.extractors.glossary import parse_glossary_entries
from fedresearch_dictionary_extractor.profiles.army import ArmyProfile

PAGE_H = 792.0
LEFT_X = 72.0


class _DodStubProfile(ArmyProfile):
    """ArmyProfile (implements all abstract members) but in inline_split mode
    with DoD-shaped invalid-term patterns. Exercises the gate without needing
    the full DodProfile (step 5)."""

    @property
    def name(self) -> str:
        return "dod-stub"

    @property
    def term_gate_mode(self) -> str:
        return "inline_split"

    @property
    def invalid_term_patterns(self) -> list[str]:
        # Structural-header NOISE only — these are dropped as whole lines
        # (never definition content). Term-rejection prefixes like
        # "Reference"/"Defined in"/"See" are NOT here: cross-refs such as
        # "BSA. Defined in Reference (k)." are VALID glossary entries.
        return [
            r"^PART\s+[IVX0-9]+\b",
            r"^SECTION\b",
            r"^GLOSSARY\b",
            r"^ABBREVIATIONS\s+AND\s+ACRONYMS\b",
            r"^Unless\s+otherwise\b",
        ]


DOD = _DodStubProfile()


def _line_spans(text: str, x: float, y: float, bold: bool = False) -> dict:
    flags = 16 if bold else 4
    return {
        "spans": [
            {"text": text, "bbox": [x, y, x + 400, y + 10], "size": 12.0, "flags": flags}
        ]
    }


def _mock_doc(lines: list[tuple[str, float]]) -> MagicMock:
    """lines = [(text, x)]; y auto-increments by 14pt from 200 (body zone,
    below HEADER_ZONE_Y=150 and above the footer band)."""
    blocks = [{"lines": [_line_spans(t, x, 200 + i * 14)]} for i, (t, x) in enumerate(lines)]
    page = MagicMock()
    page.get_text.return_value = {"blocks": blocks}
    page.rect = MagicMock()
    page.rect.height = PAGE_H
    page.get_label = MagicMock(return_value=None)
    doc = MagicMock()
    doc.__getitem__.side_effect = lambda i: page
    doc.__len__.return_value = 1
    return doc


def _terms(entries: list[dict]) -> list[str]:
    return [e["term"] for e in entries]


def test_new_term_with_inline_def() -> None:
    doc = _mock_doc([("CBR hardness.  The capability of materiel to withstand.", LEFT_X)])
    entries = parse_glossary_entries(doc, 0, 0, DOD)
    assert _terms(entries) == ["CBR hardness"]
    assert entries[0]["definition"].startswith("The capability of materiel")


def test_lowercase_continuation_is_appended_not_new_term() -> None:
    doc = _mock_doc(
        [
            ("CBR hardness.  The capability of materiel to withstand.", LEFT_X),
            ("contaminated environment without losing the mission.", LEFT_X),
        ]
    )
    entries = parse_glossary_entries(doc, 0, 0, DOD)
    assert _terms(entries) == ["CBR hardness"]
    assert "contaminated environment" in entries[0]["definition"]


def test_two_real_terms_separated() -> None:
    doc = _mock_doc(
        [
            ("DODIN.  The globally interconnected set of capabilities.", LEFT_X),
            ("materiel developer.  The organization responsible for it.", LEFT_X),
        ]
    )
    entries = parse_glossary_entries(doc, 0, 0, DOD)
    assert _terms(entries) == ["DODIN", "materiel developer"]


def test_section_header_not_a_term() -> None:
    doc = _mock_doc(
        [
            ("PART II.  DEFINITIONS", LEFT_X),
            ("BSA.  Defined in Reference (k).", LEFT_X),
        ]
    )
    entries = parse_glossary_entries(doc, 0, 0, DOD)
    assert "PART II" not in _terms(entries)
    assert "BSA" in _terms(entries)


def test_acronym_two_space_separator() -> None:
    doc = _mock_doc([("AEP  Alternate Emergency Procedures program.", LEFT_X)])
    entries = parse_glossary_entries(doc, 0, 0, DOD)
    assert _terms(entries) == ["AEP"]


def test_crossref_definition_is_a_valid_entry() -> None:
    """Cross-ref entries (term + 'Defined in Reference (x).') are real glossary
    entries — the term is kept, the pointer is its definition."""
    doc = _mock_doc([("BSA.  Defined in Reference (k).", LEFT_X)])
    entries = parse_glossary_entries(doc, 0, 0, DOD)
    assert _terms(entries) == ["BSA"]
    assert "Reference (k)" in entries[0]["definition"]


def test_capitalized_sentence_continuation_is_not_a_new_term() -> None:
    """A wrapped definition sentence starting 'The …' (capitalized stopword)
    must fold into the open definition, not split into a bogus term."""
    doc = _mock_doc(
        [
            ("EMP survivability.  The capability of a system to withstand exposure", LEFT_X),
            ("The assigned mission. The three main principles apply to it.", LEFT_X),
        ]
    )
    entries = parse_glossary_entries(doc, 0, 0, DOD)
    assert _terms(entries) == ["EMP survivability"]
    assert "the assigned mission" not in [t.lower() for t in _terms(entries)]


def test_structural_header_between_terms_does_not_pollute_defs() -> None:
    """A 'PART II. DEFINITIONS' header sitting between two terms is dropped as
    a noise line — it neither becomes a term nor pollutes either definition."""
    doc = _mock_doc(
        [
            ("CBR hardness.  The capability of materiel to withstand.", LEFT_X),
            ("PART II.  DEFINITIONS", LEFT_X),
            ("DODIN.  The globally interconnected set of capabilities.", LEFT_X),
        ]
    )
    entries = parse_glossary_entries(doc, 0, 0, DOD)
    assert _terms(entries) == ["CBR hardness", "DODIN"]
    assert "DEFINITIONS" not in entries[0]["definition"]
