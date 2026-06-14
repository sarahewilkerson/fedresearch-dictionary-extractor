"""
DodProfile — DoD-wide issuances + Joint docs (P2-B).

Covers DoD Instruction/Directive/Manual, Administrative Instruction,
Directive-Type Memorandum, DoD CPM Issuance, and (experimental) CJCS
Instruction/Manual/Notice/Guide + Joint Publication.

DoD issuance glossaries are a back-matter "GLOSSARY" enclosure with
"PART I. ABBREVIATIONS AND ACRONYMS" then "PART II. DEFINITIONS"; entries are
`Term.  Definition` (left-justified, OCR'd, no bold). Spatial/bold gating
cannot separate them, so this profile uses term_gate_mode="inline_split"
(textual new-term detection) and enable_bold_gate=False (which also
short-circuits the analyzer's legacy-gate fallback). Range detection reuses
find_glossary_page_range (largest-contiguous-block + later-position tie-break
handles the TOC-vs-body false match).
"""
import re

from .base import ReferenceProfile

# A real DoD glossary body has `Term. Definition` lines (1+ spaces after the
# period — DODI uses two, AI uses one); a TOC page is dominated by dot-leaders
# ("Title ....... 33"). Used to reject TOC blocks whose "PART II: DEFINITIONS"
# entries match the glossary header patterns. The dot-leader-dominance check
# (not the term shape alone) is what discriminates TOC from glossary.
_DOD_TERM_LINE_RE = re.compile(
    r"(?m)^\s*[A-Za-z0-9][A-Za-z0-9 /()\-\.]{0,48}?\.\s+[A-Z\"(]"
)
_DOT_LEADER_RE = re.compile(r"\.{5,}")


class DodProfile(ReferenceProfile):
    @property
    def name(self) -> str:
        return "dod"

    @property
    def term_gate_mode(self) -> str:
        return "inline_split"

    @property
    def enable_bold_gate(self) -> bool:
        # DoD definition pages are no-bold OCR; the bold gate is meaningless
        # here. False ALSO short-circuits analyzer._bold_preservation_rate
        # legacy-gate fallback (which would over-segment a left-justified
        # block). inline_split is independent of bold regardless.
        return False

    def confirm_glossary_block(self, page_texts: list[str]) -> bool:
        text = "\n".join(page_texts)
        term_lines = len(_DOD_TERM_LINE_RE.findall(text))
        dot_leaders = len(_DOT_LEADER_RE.findall(text))
        # A real DoD glossary body has many term.def lines and ~zero
        # dot-leaders; a TOC block (whose "PART II: DEFINITIONS" entries also
        # match the header patterns) is dot-leader-bearing. The dot-leader
        # count is the decisive TOC signal.
        return term_lines >= 3 and dot_leaders <= 2

    @property
    def supported_doc_types(self) -> list[str]:
        # FedResearch documents.document_type values routed to this profile
        # (informational — Phase C routes by collection→service, not this).
        # CJCS*/JP are experimental for v0.6.0 (inline-paragraph / two-column
        # glossaries, not the back-matter Term.Definition format).
        return [
            "DoD Instruction",
            "DoD Directive",
            "DoD Manual",
            "Administrative Instruction",
            "Directive-Type Memorandum",
            "DoD CPM Issuance",
            "CJCS Instruction",
            "CJCS Manual",
            "CJCS Notice",
            "CJCS Guide",
            "Joint Publication",
        ]

    @property
    def publication_patterns(self) -> list[tuple[str, str]]:
        # re.search over the filename (underscores→spaces). Order: most
        # specific first. Single-token display prefixes so the analyzer's
        # first-token doc_type derivation stays unambiguous for multi-word
        # families (DoD CPM Issuance → "DoDCPM"; CJCS Guide → "CJCSG").
        return [
            (r"\bDoDCPM\w*\s+([\d.]+(?:\s+Vol\s+\w+)?)", "DoDCPM"),
            (r"\b(?:DoDI|DODI)\s+([\d.]+)", "DoDI"),
            (r"\b(?:DoDD|DODD)\s+([\d.]+)", "DoDD"),
            (r"\b(?:DoDM|DODM)\s+([\d.]+)", "DoDM"),
            (r"\bCJCSI\s+([\dA-Z.\-]+)", "CJCSI"),
            (r"\bCJCSM\s+([\dA-Z.\-]+)", "CJCSM"),
            (r"\bCJCSN\s+([\dA-Z.\-]+)", "CJCSN"),
            (r"\bCJCS\s+Guide\s+([\dA-Z.\-]+)", "CJCSG"),
            (r"\bAI\s+(\d+[A-Z]?)", "AI"),
            (r"\bDTM\s+([\d.\-]+)", "DTM"),
            (r"\bJP\s+(\d+(?:[\s_\-]\d+)?)", "JP"),
        ]

    @property
    def glossary_header_patterns(self) -> list[str]:
        # Whole-line anchored (the find_glossary_page_range docstring requires
        # it — broad patterns false-match body text). The running "GLOSSARY"
        # header appears alone on a line on every glossary page → the
        # largest-contiguous-block tie-break selects the real back-matter
        # block over the single-line TOC reference.
        return [
            r"^\s*GLOSSARY\s*$",
            r"^\s*PART\s+[IVX]+\.?\s*[—:\-]?\s*DEFINITIONS\b",
            r"^\s*PART\s+[IVX]+\.?\s*[—:\-]?\s*ABBREVIATIONS\b",
            r"^\s*[A-Z]\.\d+\.?\s+DEFINITIONS\b",   # enclosure form "G.2. DEFINITIONS"
        ]

    @property
    def header_patterns(self) -> list[str]:
        # Running headers/footers to skip (top/bottom zones), so they don't
        # become spurious continuation text or terms.
        return [
            r"^\s*(?:DoDI|DODI|DoDD|DODD|DoDM|DODM|DoDCPM\w*|AI|DTM)\s+[\d.]+.*,\s+\w+\s+\d",
            r"^\s*Change\s+\d+,?\s+[\d/]+\s*$",
            r"^\s*GLOSSARY\s*$",
            r"^\s*CJCS[IMNG]?\s+[\dA-Z.\-]+.*,?\s+\d{1,2}\s+\w+\s+\d{4}",
        ]

    @property
    def invalid_term_patterns(self) -> list[str]:
        # Structural-header NOISE only (dropped as whole lines; never
        # definition content). NOT term-rejection prefixes like
        # "Reference"/"Defined in" — cross-refs such as
        # "BSA. Defined in Reference (k)." are valid entries.
        return [
            r"^\s*$",
            r"^[\W_]+$",
            r"^\d+$",
            r"^PART\s+\S",            # any "PART <x>" header (incl. OCR "PART Il")
            r"^SECTION\b",
            r"^GLOSSARY\b",
            r"^ABBREVIATIONS\s+AND\s+ACRONYMS\b",
            r"^Unless\s+otherwise\b",
            r"^GL[-–—]\d+\s*$",                     # JP glossary page label "GL-1"
            r"^\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\s*$",  # bare date
            r"^[A-Z]\.\d+\b",                       # enclosure label "G.1", "G.2"
            r"^U\.\s*S\.?\s*C?\.?\s*$",             # bare "U.S", "U.S.", "U.S.C"
            r"^[A-Z][a-z]+\s+[A-Z]\.?\s*$",         # signature "William E"
        ]

    @property
    def footer_patterns(self) -> list[str]:
        return [
            r"^\s*\d+\s*$",                          # bare page number
            r"^GL[-–—]\d+\s*$",                      # "GL-1"
            r"^\s*Change\s+\d+,?\s+[\d/]+\s*$",
            r"^\s*(?:DoDI|DODI|DoDD|DODD|DoDM|DODM)\s+[\d.]+,",
        ]

    @property
    def inline_definition_patterns(self) -> list[str]:
        # Generic body-text inline definitions (same shape as Army's). Each
        # captures named groups `term` and `definition`. Glossary extraction
        # is the primary path; this is a secondary net.
        return [
            r"For (?:the )?purposes of this (?:instruction|directive|manual|issuance|document|publication)(?:,)?\s+"
            r"(?P<term>[A-Z][A-Za-z0-9\s\-']{2,80}?)\s+(?:means|is defined as|shall mean|refers to)\s+"
            r"(?P<definition>[^.!?\n]{10,1500}[.!?])",
            r"The term ['\"]?(?P<term>[A-Z][A-Za-z0-9\s\-']{2,80}?)['\"]?\s+"
            r"(?:means|is defined as|shall mean|refers to)\s+"
            r"(?P<definition>[^.!?\n]{10,1500}[.!?])",
        ]

    @property
    def citation_pattern(self) -> str:
        # Strip embedded parenthetical doc citations from definition text.
        # Does NOT match "(k)" / "Reference (k)" (no doc-type prefix), so
        # cross-ref pointer definitions are preserved.
        return (
            r"\s*\(\s*(?:DoDI|DoDD|DoDM|CJCSI|CJCSM|CJCSN|JP|AI|DTM)"
            r"\s*[\d.\-]+[^)]*\)\s*"
        )

    @property
    def edge_case_documents(self) -> list[str]:
        return []
