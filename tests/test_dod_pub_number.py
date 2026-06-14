"""P2-B: DoD publication-number + doc-type derivation per family (Codex iter-1 #7).

PDF-free: drives analyzer._guess_pub_number / _guess_doc_type on realistic prod
filenames for every claimed family, incl. multi-token families (DoD CPM Issuance,
Joint Publication) where the naive first-token split could go wrong.
"""
from __future__ import annotations

import pytest

from fedresearch_dictionary_extractor.core.analyzer import _guess_doc_type, _guess_pub_number
from fedresearch_dictionary_extractor.profiles import get_profile

DOD = get_profile("dod")

CASES = [
    # (filename, expected_pub_number, expected_doc_type)
    ("DoDI 3150.09 The Chemical Survivability Policy CH4 2023_12_08_OCR.pdf", "DoDI 3150.09", "DoDI"),
    ("DoDD 7730.65 DoD Readiness Reporting System 2023_05_31_OCR.pdf", "DoDD 7730.65", "DoDD"),
    ("DoDM 4140.01 DoD Supply Chain Materiel Management CH4 2022_11_04_OCR.pdf", "DoDM 4140.01", "DoDM"),
    ("AI 31 Equal Employment Opportunity Program CH3 2025_03_12_OCR.pdf", "AI 31", "AI"),
    ("DTM 13-008 DoD Implementation of PPD 19 CH6 2025_08_04_OCR.pdf", "DTM 13-008", "DTM"),
    ("DoDCPMIssuance 1400.25 Vol 1471 NAF Labor-Management CH3 2025_07_29_OCR.pdf", "DoDCPM 1400.25 Vol 1471", "DoDCPM"),
    ("CJCSI 3205.01D JOINT COMBAT CAMERA 2014-Oct_OCR.pdf", "CJCSI 3205.01D", "CJCSI"),
    ("CJCSM 3511.01A JOINT TRAINING RESOURCES 2019-Aug_OCR.pdf", "CJCSM 3511.01A", "CJCSM"),
    ("CJCSN 4130.01 GUIDANCE FOR CCDR EMPLOYMENT 2011-Dec_OCR.pdf", "CJCSN 4130.01", "CJCSN"),
    ("CJCS Guide 3130 ADAPTIVE PLANNING 2019-Mar_OCR.pdf", "CJCSG 3130", "CJCSG"),
    # JP prod filenames use underscores between number parts; pub_number is
    # cosmetic for the (experimental) JP family — assert actual behavior.
    ("JP_1_04_OCR.pdf", "JP 1 04", "JP"),
    # Codex iter-1 #3: trailing volume letter + spaced "DoD CPM Issuance".
    ("DoDI 5000.02T Operation of the Adaptive Acquisition Framework 2022_06_08_OCR.pdf", "DoDI 5000.02T", "DoDI"),
    ("DoD CPM Issuance 1400.25 Vol 1471 NAF Labor-Management CH3 2025_07_29_OCR.pdf", "DoDCPM 1400.25 Vol 1471", "DoDCPM"),
    # compact local/fetch filename form (underscore→space normalized)
    ("DoDCPM_1400.25v1471 NAF Labor-Management CH3 2025_07_29_OCR.pdf", "DoDCPM 1400.25v1471", "DoDCPM"),
]


@pytest.mark.parametrize("filename,pub,doctype", CASES)
def test_pub_number_and_doc_type(filename: str, pub: str, doctype: str) -> None:
    assert _guess_pub_number(filename, DOD) == pub
    assert _guess_doc_type(filename, DOD) == doctype
