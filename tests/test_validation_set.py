"""
Validation harness — runs the extractor against the labeled real-PDF set
and enforces per-doc-type precision/recall + def-text Jaccard thresholds
from parent plan §H8.

OPT-IN. Marked `validation`; not run by default. Skips cleanly if
validation_set/labels.yaml or the referenced PDFs aren't present, so a
fresh clone (or CI without the PDF set) doesn't fail.

To run locally:
    pytest -m validation -v
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest
import yaml

from fedresearch_dictionary_extractor.core.analyzer import analyze_pdf
from fedresearch_dictionary_extractor.normalize import normalize_term

VALIDATION_DIR = Path(__file__).parent.parent / "validation_set"
LABELS_FILE = VALIDATION_DIR / "labels.yaml"
PDF_DIR = VALIDATION_DIR / "pdfs"

# Per-type thresholds from parent plan §H8.
# Schema: doc_type -> source_type -> (precision_min, recall_min, def_jaccard_min)
THRESHOLDS: dict[str, dict[str, tuple[float, float, float]]] = {
    "AR":  {"glossary": (0.95, 0.85, 0.85)},
    "PAM": {"glossary": (0.90, 0.80, 0.80)},
    "FM":  {"glossary": (0.85, 0.75, 0.75)},
    "ATP": {"glossary": (0.85, 0.75, 0.75)},
    "ADP": {"glossary": (0.85, 0.75, 0.75)},
    "TC":  {"glossary": (0.85, 0.75, 0.75)},
    "TM":  {"glossary": (0.85, 0.75, 0.75)},
    # Inline thresholds are applied across ALL doc types
    "*":   {"inline":   (0.75, 0.50, 0.65)},
}


def _have_labels() -> bool:
    return LABELS_FILE.exists() and LABELS_FILE.stat().st_size > 0


pytestmark = [
    pytest.mark.validation,
    pytest.mark.skipif(not _have_labels(), reason="validation_set/labels.yaml not present"),
]


def _load_labels() -> list[dict]:
    data = yaml.safe_load(LABELS_FILE.read_text(encoding="utf-8"))
    return data.get("documents", [])


def _token_set(s: str) -> set[str]:
    return set(s.lower().split())


def _jaccard(a: str, b: str) -> float:
    sa, sb = _token_set(a), _token_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _classify(extracted: list[dict], labels: list[dict]) -> tuple[int, int, int, list[float]]:
    """
    For one doc + one source_type slice:
      true_positive = labeled term_normalized appears in extracted output
      false_positive = extracted term_normalized not in labels (only counted if it
        SHOULD have been labeled — we conservatively count any extracted
        term that isn't labeled as a potential FP since the labeled set is
        sampled, not exhaustive)
      def_jaccards = jaccard score for each true-positive's definition
    """
    label_terms = {normalize_term(label["term"]): label for label in labels}
    extracted_terms = {e["term_normalized"]: e for e in extracted}

    tp = 0
    def_jaccards: list[float] = []
    for term_norm, label in label_terms.items():
        if term_norm in extracted_terms:
            tp += 1
            def_jaccards.append(
                _jaccard(extracted_terms[term_norm]["definition"], label["definition"])
            )

    fn = len(label_terms) - tp
    # Conservative FP: extracted terms not in labels.
    # Because the label set is SAMPLED (not exhaustive per doc), this overcounts;
    # use it as a soft signal only — thresholds are calibrated for labeled coverage.
    fp = sum(1 for t in extracted_terms if t not in label_terms)

    return tp, fp, fn, def_jaccards


def test_per_type_thresholds() -> None:
    """One scorecard for the whole validation set; fail if any per-type gate is breached."""
    docs = _load_labels()
    if not docs:
        pytest.skip("labels.yaml has no documents")

    # group: (doc_type, source_type) -> aggregated stats
    aggregate: dict[tuple[str, str], dict] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "jaccards": []})

    for doc_entry in docs:
        pdf_path = PDF_DIR / doc_entry["pdf"]
        if not pdf_path.exists():
            pytest.skip(f"PDF not present locally: {pdf_path}")
        doc_type = doc_entry["doc_type"]
        labels = doc_entry["labels"]

        payload = analyze_pdf(pdf_path)
        extracted = payload["entries"]

        # Split labels + extracted by source_type
        for source_type in ("glossary", "inline"):
            slice_labels = [label for label in labels if label.get("source_type") == source_type]
            slice_extracted = [e for e in extracted if e["source_type"] == source_type]
            if not slice_labels and not slice_extracted:
                continue
            tp, fp, fn, jaccards = _classify(slice_extracted, slice_labels)
            agg = aggregate[(doc_type, source_type)]
            agg["tp"] += tp
            agg["fp"] += fp
            agg["fn"] += fn
            agg["jaccards"].extend(jaccards)

    # Apply thresholds + collect failures into a single error report
    failures: list[str] = []
    scorecard: list[dict] = []
    for (doc_type, source_type), agg in sorted(aggregate.items()):
        tp, fp, fn = agg["tp"], agg["fp"], agg["fn"]
        denom_p = tp + fp
        denom_r = tp + fn
        precision = tp / denom_p if denom_p else 0.0
        recall = tp / denom_r if denom_r else 0.0
        avg_jaccard = sum(agg["jaccards"]) / len(agg["jaccards"]) if agg["jaccards"] else 0.0

        # Resolve per-type threshold (inline uses '*')
        type_key = doc_type if source_type == "glossary" else "*"
        threshold = THRESHOLDS.get(type_key, {}).get(source_type)
        if not threshold:
            continue
        p_min, r_min, j_min = threshold

        row = {
            "doc_type": doc_type,
            "source_type": source_type,
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "def_jaccard": round(avg_jaccard, 3),
            "thresholds": {"precision": p_min, "recall": r_min, "def_jaccard": j_min},
            "passed": precision >= p_min and recall >= r_min and avg_jaccard >= j_min,
        }
        scorecard.append(row)
        if not row["passed"]:
            failures.append(
                f"{doc_type}/{source_type}: precision={precision:.2f} (≥{p_min}), "
                f"recall={recall:.2f} (≥{r_min}), def_jaccard={avg_jaccard:.2f} (≥{j_min})"
            )

    # Always emit scorecard.json so PR1.2 has a real artifact to reference
    scorecard_path = VALIDATION_DIR / "scorecard.json"
    import json
    scorecard_path.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")

    if failures:
        pytest.fail("Per-type validation thresholds breached:\n  " + "\n  ".join(failures))
