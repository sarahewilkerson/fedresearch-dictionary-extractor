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
