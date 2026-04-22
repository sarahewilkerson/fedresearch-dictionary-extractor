"""
ArmyProfile — covers v1 doc types: AR, DA PAM, FM, ATP, ADP, TC, TM.
"""
from .base import ReferenceProfile


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
        return [
            r"^\d+$",  # pure number
            r"^[\W_]+$",  # all punctuation
            r"^\s*$",  # whitespace-only
            r"^(AR|FM|ADP|ATP|TC|PAM|TM)\s+\d+[-–]\d+\s*$",  # just a citation
            r"^(Figure|Table|Chapter|Appendix|Section)\s+[A-Z0-9]",
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
