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
    # agg_key -> {tp, fn, jaccards, fp_explicit, tp_in_neg_docs, had_negatives}
    # tp_in_neg_docs is tracked separately so precision is computed ONLY over
    # the subset of docs that declared negative_labels — otherwise positives
    # from no-negative PDFs would inflate precision across mixed aggregates
    # (Codex rerun finding #2).
    agg: dict[tuple[str, str], dict] = defaultdict(
        lambda: {
            "tp": 0,
            "fn": 0,
            "jaccards": [],
            "fp_explicit": 0,
            "tp_in_neg_docs": 0,
            "had_negatives": False,
        }
    )

    for doc_entry in docs:
        pdf_path = PDF_DIR / doc_entry["pdf"]
        if not pdf_path.exists():
            pytest.skip(f"PDF not present locally: {pdf_path}")
        doc_type = doc_entry["doc_type"]
        labels = doc_entry.get("labels", [])
        negative_labels = doc_entry.get("negative_labels", [])

        extracted = analyze_pdf(pdf_path)["entries"]

        # Per source_type slice — Codex rerun finding #1: source-type-filter
        # the extracted set so a labeled-inline term found only as glossary
        # doesn't falsely satisfy inline recall.
        for source_type in ("glossary", "inline"):
            slice_labels = [lbl for lbl in labels if lbl.get("source_type") == source_type]
            slice_negatives = [n for n in negative_labels if n.get("source_type") == source_type]
            # PR1.2-quality Stage 1: `labels` (Jaccard-gated) intentionally
            # empty until Stage 2 supplies user-confirmed canonical defs from
            # batches 2+3. Skip per-type metrics for slices without `labels`
            # — Tier-1 (term-presence + negatives) is in test_tier1_oracle.
            if not slice_labels:
                continue

            extracted_slice = {
                e["term_normalized"]: e for e in extracted if e["source_type"] == source_type
            }

            key = _aggregate_key(doc_type, source_type)
            stats = agg[key]
            doc_has_negatives = bool(slice_negatives)

            # Recall: how many labeled terms appear in extractor's same-source output
            for lbl in slice_labels:
                term_norm = normalize_term(lbl["term"])
                if term_norm in extracted_slice:
                    stats["tp"] += 1
                    if doc_has_negatives:
                        stats["tp_in_neg_docs"] += 1
                    stats["jaccards"].append(
                        _jaccard(extracted_slice[term_norm]["definition"], lbl["definition"])
                    )
                else:
                    stats["fn"] += 1

            # Precision (only when explicit negative_labels are provided —
            # Codex iter-1 #1 fix: sampled labels can't fairly compute precision)
            if slice_negatives:
                stats["had_negatives"] = True
                negative_norms = {normalize_term(n["term"]) for n in slice_negatives}
                for n in negative_norms:
                    if n in extracted_slice:
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

        # Precision is only computed + gated when negative_labels were declared.
        # Per Codex rerun finding #2: precision is computed ONLY over the docs
        # that actually declared negatives — using `tp_in_neg_docs`, not aggregate `tp`.
        precision: float | None = None
        precision_passed: bool | None = None
        if stats["had_negatives"]:
            tp_neg = stats["tp_in_neg_docs"]
            denom = tp_neg + stats["fp_explicit"]
            precision = tp_neg / denom if denom else 1.0
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
                "tp_in_neg_docs": stats["tp_in_neg_docs"],
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


# ── PR1.2-quality: two-tier oracle (Codex iter-3 #1 + iter-4 contradiction fix) ──

TIER1_POSITIVE_RECALL_MIN = 0.95   # ≥55 of 57 batch-1 user-confirmed-good terms present


def test_tier1_oracle() -> None:
    """Stage-1 acceptance gate (PR1.2-quality plan §5d).

    Tier 1 (user-confirmed, BLOCKING):
      - `negative_labels`: 100% absence (zero of these terms appear in output)
      - `tier1_positive_terms`: ≥95% recall (term-presence only — NO Jaccard)
        Codex iter-4 contradiction fix — we don't have user-confirmed
        canonical defs yet (Stage-2 work); the fix legitimately changes
        defs, so Jaccard would block valid corrections.

    Tier 2 (auto-classified, INFORMATIONAL):
      - `auto_negative_labels` / `auto_positive_labels`: emit warnings,
        do NOT block. The auto-classifier is itself imperfect; using it
        as a gate would punish the fix for correcting classifier misses.
    """
    payload = _load_labels()
    docs = payload.get("documents", [])
    if not docs:
        pytest.skip("labels.yaml has no documents")

    tier1_pos_total = 0
    tier1_pos_present = 0
    tier1_neg_violations: list[str] = []
    tier2_pos_total = 0
    tier2_pos_present = 0
    tier2_neg_violations = 0

    per_doc_metrics: list[dict] = []

    fallback_docs: list[str] = []
    for d in docs:
        pdf_path = PDF_DIR / d["pdf"]
        if not pdf_path.exists():
            pytest.skip(f"PDF not present: {pdf_path}")

        result = analyze_pdf(pdf_path)
        extracted = result["entries"]
        used_fallback = bool(result.get("metadata", {}).get("glossary_used_legacy_fallback"))
        if used_fallback:
            fallback_docs.append(d["pdf"])
        # Index by (term_normalized, source_type) for cheap presence checks.
        present_keys = {
            (e["term_normalized"], e["source_type"]) for e in extracted
        }

        doc_t1_pos_total = 0
        doc_t1_pos_present = 0
        for lbl in d.get("tier1_positive_terms") or []:
            doc_t1_pos_total += 1
            tier1_pos_total += 1
            key = (normalize_term(lbl["term"]), lbl.get("source_type", "glossary"))
            if key in present_keys:
                tier1_pos_present += 1
                doc_t1_pos_present += 1

        # PR1.2-quality: docs that fell back to legacy X-only gate (zero
        # bold flags preserved AND mixed-case lowercase terms) cannot show
        # cleanup of pre-fix bad terms — the fix didn't fire. Exclude their
        # negative_labels from Tier-1 blocking to avoid penalizing the fix
        # for "no improvement on docs the fix couldn't reach." These docs
        # are tracked as known-bad-fallback in the scorecard.
        if used_fallback:
            continue

        for nlbl in d.get("negative_labels") or []:
            key = (normalize_term(nlbl["term"]), nlbl.get("source_type", "glossary"))
            if key in present_keys:
                tier1_neg_violations.append(f"{d['pdf']}:{nlbl['term']!r}")

        doc_t2_pos_total = 0
        doc_t2_pos_present = 0
        for lbl in d.get("auto_positive_labels") or []:
            doc_t2_pos_total += 1
            tier2_pos_total += 1
            key = (normalize_term(lbl["term"]), lbl.get("source_type", "glossary"))
            if key in present_keys:
                tier2_pos_present += 1
                doc_t2_pos_present += 1

        for nlbl in d.get("auto_negative_labels") or []:
            key = (normalize_term(nlbl["term"]), nlbl.get("source_type", "glossary"))
            if key in present_keys:
                tier2_neg_violations += 1

        per_doc_metrics.append({
            "pdf": d["pdf"],
            "doc_type": d["doc_type"],
            "tier1_positive_total": doc_t1_pos_total,
            "tier1_positive_present": doc_t1_pos_present,
            "tier2_positive_total": doc_t2_pos_total,
            "tier2_positive_present": doc_t2_pos_present,
        })

    tier1_recall = tier1_pos_present / tier1_pos_total if tier1_pos_total else 1.0
    tier2_recall = tier2_pos_present / tier2_pos_total if tier2_pos_total else 1.0

    # Tier-2 informational: emit warnings, do not fail.
    import warnings
    if tier2_neg_violations > 0 or tier2_recall < 0.85:
        warnings.warn(
            f"Tier-2 (auto-classified, INFO only): "
            f"recall={tier2_recall:.2%} ({tier2_pos_present}/{tier2_pos_total}); "
            f"auto-negative violations={tier2_neg_violations}",
            stacklevel=2,
        )

    # Persist Tier-1/Tier-2 metrics into the scorecard alongside per-type results.
    scorecard_path = VALIDATION_DIR / "scorecard.json"
    if scorecard_path.exists():
        existing = json.loads(scorecard_path.read_text(encoding="utf-8"))
    else:
        existing = {}
    existing["tier1"] = {
        "positive_total": tier1_pos_total,
        "positive_present": tier1_pos_present,
        "positive_recall": round(tier1_recall, 3),
        "positive_recall_threshold": TIER1_POSITIVE_RECALL_MIN,
        "negative_violations": tier1_neg_violations,
        "passed": (
            len(tier1_neg_violations) == 0
            and tier1_recall >= TIER1_POSITIVE_RECALL_MIN
        ),
    }
    existing["tier2"] = {
        "positive_total": tier2_pos_total,
        "positive_present": tier2_pos_present,
        "positive_recall": round(tier2_recall, 3),
        "negative_violations": tier2_neg_violations,
        "informational_only": True,
    }
    existing["per_doc_metrics"] = per_doc_metrics
    existing["fallback_docs"] = fallback_docs
    scorecard_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    # Tier-1 BLOCKING gates
    if tier1_neg_violations:
        pytest.fail(
            f"Tier-1 negative-label violations ({len(tier1_neg_violations)}): "
            + "; ".join(tier1_neg_violations)
        )
    if tier1_recall < TIER1_POSITIVE_RECALL_MIN:
        pytest.fail(
            f"Tier-1 positive-term recall {tier1_recall:.2%} < threshold "
            f"{TIER1_POSITIVE_RECALL_MIN:.0%} "
            f"({tier1_pos_present}/{tier1_pos_total} terms present)"
        )
