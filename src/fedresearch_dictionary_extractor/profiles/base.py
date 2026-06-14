"""
Profile base class — defines the interface every doc-family profile must implement.
"""
from abc import ABC, abstractmethod


class ReferenceProfile(ABC):
    """Abstract base for document-family profiles (Army, DoD, etc.)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Profile identifier (e.g., 'army')."""

    @property
    @abstractmethod
    def publication_patterns(self) -> list[tuple[str, str]]:
        """
        Regex patterns for extracting publication type + number from filenames.
        Each tuple: (regex, display_prefix).
        """

    @property
    @abstractmethod
    def glossary_header_patterns(self) -> list[str]:
        """Regex patterns identifying the start of a glossary section."""

    @property
    @abstractmethod
    def header_patterns(self) -> list[str]:
        """
        Regex patterns identifying document-level headers/footers to skip
        (e.g., 'HEADQUARTERS / DEPARTMENT OF THE ARMY').
        """

    @property
    @abstractmethod
    def invalid_term_patterns(self) -> list[str]:
        """Regex patterns rejecting glossary-line candidates that look like noise."""

    @property
    @abstractmethod
    def inline_definition_patterns(self) -> list[str]:
        """
        Regex patterns for inline definitions scanned in body text
        (e.g., 'For purposes of this regulation, X means Y').
        Each pattern MUST capture named groups `term` and `definition`.
        """

    @property
    @abstractmethod
    def citation_pattern(self) -> str:
        """Regex for embedded citations in definition text, to be stripped."""

    @property
    @abstractmethod
    def edge_case_documents(self) -> list[str]:
        """Filename patterns to exclude outright (known-broken documents)."""

    @property
    @abstractmethod
    def supported_doc_types(self) -> list[str]:
        """Canonical doc_type strings this profile is responsible for."""

    # ── Non-abstract defaults (PR1.2-quality additions) ──────────────────
    # These have safe defaults so existing profiles keep working without
    # implementing them; subclasses override when they have content.

    @property
    def footer_patterns(self) -> list[str]:
        """
        Regex patterns identifying page-footer text (bare dates, doc-id +
        bullet + page, "Glossary-N" labels). Matched in the bottom-zone Y
        band and rejected, so footer text doesn't bleed into adjacent
        glossary definitions.

        Default: empty list. Override in subclass when footer noise is
        observed in real PDFs.
        """
        return []

    @property
    def term_gate_mode(self) -> str:
        """New-term detection strategy for the glossary parser.

        - ``"spatial"`` (default): Army convention — a left-margin line is a
          new term when its first span is bold OR acronym-shaped (the
          bold/X-position gate). Continuation lines wrap to the left margin.
        - ``"inline_split"``: DoD/issuance convention — definition pages are
          fully left-justified (term AND continuation at the same x) and
          OCR'd (no bold), so spatial/bold gating cannot separate entries.
          A line is a new term iff it matches ``inline_split_pattern``
          (``Term.  Definition`` / ``ACRONYM  expansion``) AND the candidate
          term validates; everything else is a continuation. Independent of
          x-position, bold flags, and the legacy-gate fallback.

        Default ``"spatial"`` so existing profiles are unaffected.
        """
        return "spatial"

    @property
    def inline_split_pattern(self) -> str | None:
        """Override the term/definition split regex used in ``inline_split``
        mode. ``None`` (default) reuses the parser's module-level ``split_re``
        (``^Term <sep> Definition`` with the Army character set). Override only
        when a family's term separators / first-definition chars / term
        char-set diverge from Army's — keeps the shared ``split_re`` untouched.
        """
        return None

    def confirm_glossary_block(self, page_texts: list[str]) -> bool:
        """Given the page texts of a candidate glossary block (the matching
        pages plus a little following context), return whether it is a REAL
        glossary body rather than a table-of-contents / appendix false match.

        Default: ``True`` (no confirmation — preserves existing behavior for
        profiles whose header patterns are TOC-safe). Override when broad
        header tokens can match TOC entries (e.g. DoD's "PART II: DEFINITIONS"
        appears both in the TOC and at the real back-matter glossary).
        """
        return True

    @property
    def enable_bold_gate(self) -> bool:
        """
        Toggle the bold/ALL-CAPS new-term gate added in PR1.2-quality.

        When True (default): a left-margin line is treated as a NEW term
        only when its first span is bold OR the line looks like an
        acronym-section term (per `_looks_like_acronym_term_line`).
        Continuation lines that wrap to the left margin are kept as
        definition text.

        When False: revert to legacy X-position-only gating. Escape
        hatch for forensics on PDFs that lose bold flags AND don't use
        ALL-CAPS terms.
        """
        return True
