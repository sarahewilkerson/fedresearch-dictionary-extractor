"""
Validation harness — runs the extractor against the labeled real-PDF set
and enforces per-doc-type recall + def-text Jaccard thresholds from
parent plan §H8 (precision is gated only when explicit negative_labels
are present, since sampled label sets cannot fairly compute precision).

OPT-IN. Marked `validation`; not run by default. Skips cleanly if
validation_set/labels.yaml or the referenced PDFs aren't present, so a
fresh clone (or CI without the PDF set) doesn't fail.

To run locally:
    pytest -m validation -v
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest
import yaml

from fedresearch_dictionary_extractor.core.analyzer import analyze_pdf
from fedresearch_dictionary_extractor.normalize import normalize_term

VALIDATION_DIR = Path(__file__).parent.parent / "validation_set"
LABELS_FILE = VALIDATION_DIR / "labels.yaml"
PDF_DIR = VALIDATION_DIR / "pdfs"

# Per-type thresholds from parent plan §H8. (precision_min, recall_min, def_jaccard_min).
# Precision is enforced ONLY when explicit negative_labels are provided per PDF.
# Otherwise the harness reports it as informational and gates on recall + def_jaccard.
THRESHOLDS: dict[tuple[str, str], tuple[float, float, float]] = {
    ("AR",  "glossary"): (0.95, 0.85, 0.85),
    ("PAM", "glossary"): (0.90, 0.80, 0.80),
    ("FM",  "glossary"): (0.85, 0.75, 0.75),
    ("ATP", "glossary"): (0.85, 0.75, 0.75),
    ("ADP", "glossary"): (0.85, 0.75, 0.75),
    ("TC",  "glossary"): (0.85, 0.75, 0.75),
    ("TM",  "glossary"): (0.85, 0.75, 0.75),
    # Inline thresholds are applied across ALL doc types (overall aggregate).
    ("*",   "inline"):   (0.75, 0.50, 0.65),
}


def _have_labels() -> bool:
    return LABELS_FILE.exists() and LABELS_FILE.stat().st_size > 0


pytestmark = [
    pytest.mark.validation,
    pytest.mark.skipif(not _have_labels(), reason="validation_set/labels.yaml not present"),
]


def _load_labels() -> dict:
    return yaml.safe_load(LABELS_FILE.read_text(encoding="utf-8")) or {}


def _token_set(s: str) -> set[str]:
    return set(s.lower().split())


def _jaccard(a: str, b: str) -> float:
    sa, sb = _token_set(a), _token_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _aggregate_key(doc_type: str, source_type: str) -> tuple[str, str]:
    """Inline thresholds are documented as overall (*) — collapse doc_type for inline."""
    if source_type == "inline":
        return ("*", "inline")
    return (doc_type, source_type)


def test_per_type_thresholds() -> None:
    """One scorecard for the whole validation set; fail if any per-type gate is breached."""
    payload = _load_labels()
    docs = payload.get("documents", [])
    if not docs:
        pytest.skip("labels.yaml has no documents")

    # 1. Stratification gate (Codex iter-1 #3 fix): require labels.yaml to declare
    #    its expected stratification, and fail loudly if actual labeled docs
    #    don't match. Otherwise a partial corpus would silently emit a
    #    "passing" scorecard that PR1.2 would trust incorrectly.
    expected = payload.get("expected_stratification", {})
    if not expected:
        pytest.fail(
            "labels.yaml is missing the `expected_stratification:` block. "
            "Define the expected per-doc-type counts (e.g., AR: 15, PAM: 5, ...) "
            "to gate the scorecard against incomplete coverage."
        )
    actual_counts: dict[str, int] = defaultdict(int)
    for d in docs:
        actual_counts[d["doc_type"]] += 1
    missing: list[str] = []
    for doc_type, want in expected.items():
        have = actual_counts.get(doc_type, 0)
        if have < want:
            missing.append(f"{doc_type}: have {have}, want {want}")
    if missing:
        pytest.fail(
            "Stratification gate failed (incomplete labeled corpus):\n  " + "\n  ".join(missing)
        )

    # 2. Run extractor + collect stats per (aggregate_key) slice.
    # agg_key -> {tp, fn, jaccards, fp_explicit (only when negative_labels present)}
    agg: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"tp": 0, "fn": 0, "jaccards": [], "fp_explicit": 0, "had_negatives": False}
    )

    for doc_entry in docs:
        pdf_path = PDF_DIR / doc_entry["pdf"]
        if not pdf_path.exists():
            pytest.skip(f"PDF not present locally: {pdf_path}")
        doc_type = doc_entry["doc_type"]
        labels = doc_entry.get("labels", [])
        negative_labels = doc_entry.get("negative_labels", [])

        extracted = analyze_pdf(pdf_path)["entries"]
        extracted_by_norm = {e["term_normalized"]: e for e in extracted}

        # Per source_type slice
        for source_type in ("glossary", "inline"):
            slice_labels = [lbl for lbl in labels if lbl.get("source_type") == source_type]
            slice_negatives = [n for n in negative_labels if n.get("source_type") == source_type]
            if not slice_labels and not slice_negatives:
                continue

            key = _aggregate_key(doc_type, source_type)
            stats = agg[key]

            # Recall: how many labeled terms appear in extractor output
            for lbl in slice_labels:
                term_norm = normalize_term(lbl["term"])
                if term_norm in extracted_by_norm:
                    stats["tp"] += 1
                    stats["jaccards"].append(
                        _jaccard(extracted_by_norm[term_norm]["definition"], lbl["definition"])
                    )
                else:
                    stats["fn"] += 1

            # Precision (only when explicit negative_labels are provided —
            # Codex iter-1 #1 fix: sampled labels can't fairly compute precision)
            if slice_negatives:
                stats["had_negatives"] = True
                negative_norms = {normalize_term(n["term"]) for n in slice_negatives}
                for n in negative_norms:
                    if n in extracted_by_norm and any(
                        e["term_normalized"] == n and e["source_type"] == source_type
                        for e in extracted
                    ):
                        stats["fp_explicit"] += 1

    # 3. Apply thresholds + assemble scorecard.
    scorecard: list[dict] = []
    failures: list[str] = []
    for (label_key, source_type), stats in sorted(agg.items()):
        threshold = THRESHOLDS.get((label_key, source_type))
        if not threshold:
            continue
        p_min, r_min, j_min = threshold

        tp, fn = stats["tp"], stats["fn"]
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        avg_jaccard = sum(stats["jaccards"]) / len(stats["jaccards"]) if stats["jaccards"] else 0.0

        # Precision is only computed + gated when negative_labels were declared
        precision: float | None = None
        precision_passed: bool | None = None
        if stats["had_negatives"]:
            denom = tp + stats["fp_explicit"]
            precision = tp / denom if denom else 1.0
            precision_passed = precision >= p_min

        recall_passed = recall >= r_min
        jaccard_passed = avg_jaccard >= j_min
        all_passed = recall_passed and jaccard_passed and (precision_passed is not False)

        scorecard.append(
            {
                "doc_type_or_overall": label_key,
                "source_type": source_type,
                "tp": tp,
                "fn": fn,
                "fp_explicit": stats["fp_explicit"],
                "had_negative_labels": stats["had_negatives"],
                "recall": round(recall, 3),
                "precision": round(precision, 3) if precision is not None else None,
                "def_jaccard": round(avg_jaccard, 3),
                "thresholds": {"precision": p_min, "recall": r_min, "def_jaccard": j_min},
                "passed": all_passed,
            }
        )

        if not all_passed:
            details = [f"recall={recall:.2f} (≥{r_min})", f"def_jaccard={avg_jaccard:.2f} (≥{j_min})"]
            if precision is not None:
                details.append(f"precision={precision:.2f} (≥{p_min})")
            failures.append(f"{label_key}/{source_type}: " + ", ".join(details))

    # 4. Always emit scorecard.json — but only mark it canonical if stratification
    #    + per-type gates passed. PR1.2 should refuse to publish unless this file
    #    has `passed_all: true` at the top level.
    output = {
        "passed_all": not failures,
        "expected_stratification": expected,
        "actual_counts": dict(actual_counts),
        "rows": scorecard,
    }
    (VALIDATION_DIR / "scorecard.json").write_text(json.dumps(output, indent=2), encoding="utf-8")

    if failures:
        pytest.fail("Per-type validation thresholds breached:\n  " + "\n  ".join(failures))
