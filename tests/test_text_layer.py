"""
Tests for has_text_layer's distributed-sampling logic.

Codex iter-1 of post-PR1 review caught that the original first-5-pages-only
check would falsely classify docs with image-only front matter as no-text-layer.
"""
from unittest.mock import MagicMock

from fedresearch_dictionary_extractor.extractors.text import has_text_layer


def _fake_doc(pages: list[str]):
    """Build a minimal fake fitz.Document where each page returns the given text."""
    doc = MagicMock()
    doc.__len__.return_value = len(pages)

    page_objs: list[MagicMock] = []
    for content in pages:
        p = MagicMock()
        p.get_text.return_value = content
        page_objs.append(p)

    def _getitem(idx: int) -> MagicMock:
        return page_objs[idx]

    doc.__getitem__.side_effect = _getitem
    return doc


def test_empty_doc_returns_false() -> None:
    assert has_text_layer(_fake_doc([])) is False


def test_short_doc_with_text() -> None:
    doc = _fake_doc(["x" * 200] * 3)
    assert has_text_layer(doc) is True


def test_short_doc_image_only() -> None:
    doc = _fake_doc([""] * 3)
    assert has_text_layer(doc) is False


def test_image_only_front_matter_with_text_body_is_detected() -> None:
    """The Codex finding case: empty front matter, real body."""
    pages = [""] * 8 + ["substantive body text " * 20] * 100
    doc = _fake_doc(pages)
    assert has_text_layer(doc) is True


def test_image_only_throughout_correctly_returns_false() -> None:
    pages = [""] * 100
    doc = _fake_doc(pages)
    assert has_text_layer(doc) is False


def test_text_only_in_back_third_is_still_detected() -> None:
    pages = [""] * 80 + ["text body " * 30] * 20
    doc = _fake_doc(pages)
    assert has_text_layer(doc) is True
