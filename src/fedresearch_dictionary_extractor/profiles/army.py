"""
ArmyProfile — covers v1 doc types: AR, DA PAM, FM, ATP, ADP, TC, TM.
"""
import re

from .base import ReferenceProfile

# OCR-tolerant Section header detection (Unit 2 of v0.2.0).
# Patterns match ONLY OCR forms observed in production AR PDFs (per
# validation_set/manifest_audit.md + AR 380-381 page 84/88/90 inspection):
#   - SECTION_II_HEADER: "Section II" (canonical) + "Section Il"
#     (capital I + lowercase L; AR 380-381 page 88)
#   - SECTION_I_HEADER:  "Section I" (canonical) + "Section |"
#     (single pipe; AR 380-381 page 84) + "Section l" (lowercase L)
# Negative lookahead on SECTION_I_HEADER prevents matching Section II/Il.
# re.MULTILINE makes ^ match line-starts in multi-line page text.
SECTION_II_HEADER = re.compile(
    # Trailing constraint added in Unit 3: require end-of-line OR
    # recognized section-style suffix to avoid matching body-text lines
    # that begin with "Section II policies/regulations/...".
    r"^\s*Section\s+(?:II|Il)(?:\s*$|\s+(?:—|–|-|Terms|Other|Special|Subjects))",
    re.IGNORECASE | re.MULTILINE,
)
SECTION_I_HEADER = re.compile(
    r"^\s*Section\s+(?:I|\||l)(?![Il\|])(?:\s*$|\s+(?:—|–|-|Abbreviations|Acronyms))",
    re.IGNORECASE | re.MULTILINE,
)
# Unit 3: matches any section header AFTER Section II (III/IV/V/VI/VII).
# Used to detect the end of Section II content during range narrowing.
# OCR variants: III/Ill/lll, IV/lV/|V.
SECTION_AFTER_II_HEADER = re.compile(
    r"^\s*Section\s+(?:III|Ill|lll|IV|lV|\|V|V|VI|VII)"
    r"(?:\s*$|\s+(?:—|–|-|Special|Subjects|Other|Terms|References))",
    re.IGNORECASE | re.MULTILINE,
)


class ArmyProfile(ReferenceProfile):
    @property
    def name(self) -> str:
        return "army"

    @property
    def supported_doc_types(self) -> list[str]:
        # Matches FedResearch documents.document_type values per backend assumption A9.
        return ["AR", "PAM", "FM", "ATP", "ADP", "TC", "TM"]

    @property
    def publication_patterns(self) -> list[tuple[str, str]]:
        return [
            (r"^(AR)\s*(\d+[-–]\d+)", "AR"),
            (r"^(DA[\s_-]?PAM|PAM)\s*(\d+[-–]\d+)", "DA PAM"),
            (r"^(FM)\s*(\d+[-–]\d+)", "FM"),
            (r"^(ATP)\s*(\d+[-–]\d+(?:\.\d+)?)", "ATP"),
            (r"^(ADP)\s*(\d+[-–]\d+)", "ADP"),
            (r"^(TC)\s*(\d+[-–]\d+(?:\.\d+)?)", "TC"),
            (r"^(TM)\s*(\d+[-–]\d+(?:\.\d+)?)", "TM"),
        ]

    @property
    def glossary_header_patterns(self) -> list[str]:
        return [
            r"^\s*Glossary\s*$",
            r"^\s*GLOSSARY\s*$",
            r"^\s*Section\s+II\s*[-–—]?\s*Terms\s*$",
            r"^\s*Terms\s+and\s+Abbreviations\s*$",
            r"^\s*Acronyms\s+and\s+Abbreviations\s*$",
        ]

    @property
    def header_patterns(self) -> list[str]:
        return [
            r"HEADQUARTERS\s*\n?\s*DEPARTMENT\s+OF\s+THE\s+ARMY",
            r"By Order of the Secretary of the Army",
            r"SUMMARY of CHANGE",
            r"^\s*(AR|FM|ADP|ATP|TC|PAM|TM|DA\s*PAM)\s+\d+[-–]\d+\s*[•·]\s*\d+\s+\w+\s+\d{4}\s*$",
        ]

    @property
    def invalid_term_patterns(self) -> list[str]:
        # Compiled with re.IGNORECASE in glossary.py — case variants
        # like "unclassified" or "section" are caught.
        return [
            r"^\d+$",  # pure number
            r"^[\W_]+$",  # all punctuation
            r"^\s*$",  # whitespace-only
            r"^(AR|FM|ADP|ATP|TC|PAM|TM)\s+\d+[-–]\d+\s*$",  # just a citation
            # v0.2.a — pre-hyphen citation fragment. Rejects "AR 124",
            # "FM 6", etc. when bold markup splits on hyphen in
            # "(AR 124-210)". Structurally safe: Army doctrine always
            # identifies publications as <TYPE> <series>-<publication>;
            # a bare <TYPE> <digits> glossary headword cannot be legit.
            r"^(AR|FM|ADP|ATP|TC|PAM|TM|DA\s*PAM)\s+\d+\s*$",
            r"^(Figure|Table|Chapter|Appendix|Section)\s+[A-Z0-9]",
            # PR1.2-quality additions — observed noise terms from
            # batch-1 user spot-check (validation_set/labels-batch1.yaml).
            r"^SECTION(\s+[IVX]+)?\s*$",        # SECTION, SECTION I, SECTION II
            r"^Glossary[\s\-–—]+\d+\s*$",       # "Glossary-4", "Glossary 3"
            r"^TERMS?\s*$",                     # "TERMS", "TERM"
            r"^ACRONYMS?(\s+AND\s+ABBREVIATIONS?)?\s*$",
            r"^PIN\s+\d{4,}",                   # "PIN 123456-000"
            r"^UNCLASSIFIED\b",                 # back-cover marker
            r"^U\.\s*S\.?\s*Army\s*$",          # "U.S Army" / "U.S. Army"
            r"^U\.\s*S\.?\s*$",                 # bare "U.S"
            r"^\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\s*$",  # "08 September 2025"
            r"^This\s+(page|section)\s+intentionally\s+left\s+blank",
        ]

    @property
    def footer_patterns(self) -> list[str]:
        # PR1.2-quality Fix B — footer-zone-only filter, applied in addition
        # to is_document_header. Catches bare-date / page-number / doc-id
        # variants that header_patterns misses.
        return [
            r"^\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\s*$",                  # "30 October 2023"
            r"^[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}\s*$",                # "October 30, 2023"
            r"^\s*\d+\s*$",                                          # bare page number
            r"^(?:AR|FM|ADP|ATP|TC|PAM|TM|DA\s*PAM)\s+\d+[-–]?\d*\s*[•·\-]\s*\d+\s+\w+",
            r"^Glossary[\s\-–—]?\d*\s*$",                            # "Glossary-3"
        ]

    @property
    def inline_definition_patterns(self) -> list[str]:
        # Minimal v1 set; expand in v1.1+ based on validation results.
        # Each pattern captures named groups `term` and `definition`.
        return [
            # "For purposes of this regulation, X means Y."
            r"For (?:the )?purposes of this (?:regulation|document|pamphlet|publication|chapter)(?:,)?\s+"
            r"(?P<term>[A-Z][A-Za-z0-9\s\-']{2,80}?)\s+(?:means|is defined as|shall mean|refers to)\s+"
            r"(?P<definition>[^.!?\n]{10,1500}[.!?])",
            # "The term 'X' means Y."
            r"The term ['\"]?(?P<term>[A-Z][A-Za-z0-9\s\-']{2,80}?)['\"]?\s+"
            r"(?:means|is defined as|shall mean|refers to)\s+"
            r"(?P<definition>[^.!?\n]{10,1500}[.!?])",
        ]

    @property
    def citation_pattern(self) -> str:
        return (
            r"\s*\(\s*(?:AR|FM|ADP|ATP|TC|PAM|JP|DA\s*PAM|DA|TM|DoDI|DoDD)"
            r"\s*\d+[-–—]?\s*\d*[^)]*\)\s*"
        )

    @property
    def edge_case_documents(self) -> list[str]:
        # Files known to be unusable (corrupted OCR, non-standard structure).
        # Grow this list based on production signal.
        return []
