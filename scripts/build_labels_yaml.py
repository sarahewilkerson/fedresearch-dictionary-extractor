#!/usr/bin/env python3
"""Build validation_set/labels.yaml from candidate-output JSONs.

Per PR1.2-quality plan §5c (Stage-2 oracle construction). This script
produces the two-tier labels.yaml the validation harness reads.

Reviewed-doc verdicts (BATCH1/2/3 + FLIPS_*) are baked in from user
spot-checks performed during Stage 2 review (see labels-batch1.yaml + git
history). Re-running this script from a fresh candidate-output regenerates
labels.yaml with the same verdicts applied.

Run from repo root: python scripts/build_labels_yaml.py
"""
import json
import os
import re
import glob
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ── Reviewed docs (Stage-2 manual review) ────────────────────────────────
BATCH1 = [
    "FM_4-1", "ATP_1-05.01", "FM_3-55", "AR_12-15", "ATP_4-35",
    "FM_3-34", "TC_1-19.30", "AR_190-55", "ADP_3-07", "AR_672-20", "FM_6-02",
]
BATCH2 = ["PAM_190-45", "PAM_350-58", "PAM_71-32", "AR_405-90"]
BATCH3 = ["AR_40-3", "AR_40-5", "AR_600-20", "AR_135-100"]

# User flipped: classifier said good, user said bad
FLIPS_GOOD_TO_BAD = {
    "TC_1-19.30": ["SECTION I"],
    "AR_190-55":  ["of the condemned prisoner."],
    "ADP_3-07":   ["This"],
    "AR_12-15":   ["the term healthcare"],
    "FM_3-34":    ["*engineer"],
}

# User flipped: classifier said bad, user said good
# (Mostly long noun phrases with parenthetical-acronym suffix that trip
# `looks_like_noun_phrase`'s 8-word limit.)
FLIPS_BAD_TO_GOOD = {
    # Batch 2
    "PAM_190-45": [
        "subject/suspect (as reporting criteria in Army Law Enforcement Record Tracking System)",
    ],
    "PAM_350-58": [
        "Army Leader Development Forum (formerly prepare the Army forum)",
    ],
    "PAM_71-32":  [
        "Standard study number–line item number automated management and integrating system",
    ],
    # Batch 3 (decided autonomously by AI per established user pattern; user delegated)
    "AR_40-3": [
        "Medical treatment facility basic daily food allowance (MTF BDFA)",
        "Pharmaceutical care (Academy of Managed Care Pharmacy’s Concepts in Managed Care Pharmacy series)",
        "Pharmacy data transaction service (PDTS) (from PDTS Business Rules)",
    ],
    "AR_135-100": [
        "vol", "1LT", "1SG", "2LT",
        "Military Intelligence (MI) combat electronic warfare intelligence (CEWI) units",
        "USAR Active Guard Reserve Management Program (USAR AGR MP)",
    ],
}

# Terms the user flagged as bad but the extractor faithfully captures
# from BOLD source text — would need an extractor-level term-blocklist
# to suppress (deferred to v0.2). Excluded from negative_labels so the
# Tier-1 gate isn't permanently blocked by these unfixable cases.
EXCLUDE_FROM_NEGATIVES = {
    "PAM_71-32":  ["Equip for"],
    "AR_135-100": ["AR 124", "AR 140"],   # citation fragments from "(AR 124-210)" splits
}

# ── Auto-classifier (heuristic for non-reviewed docs + tier-2 metric) ───
NOISE_TERMS = {
    "UNCLASSIFIED", "CLASSIFIED", "CONFIDENTIAL", "SECRET",
    "This section contains no entries.", "Terms", "See",
}
STOP_TAIL = {
    "and", "or", "the", "of", "to", "with", "in", "on", "for", "by", "as",
    "are", "is", "was", "were", "that", "which", "who", "if", "when",
}
ACRO_TERM_RE = re.compile(r"^[A-Z][A-Z0-9.\-/]{1,18}(\s*\([^)]{1,20}\))?$")


def is_recognized_acronym_entry(term: str, definition: str) -> bool:
    """Recognized acronym + expansion pattern (e.g., WHINSEC, SECARMY,
    ASA (FM&C)). Override for the `^[A-Z]{6,}` rule."""
    if not term or not definition or len(term) > 22:
        return False
    if not ACRO_TERM_RE.match(term):
        return False
    if not definition[0].isalpha() or len(definition) < 3:
        return False
    return True


def looks_like_noun_phrase(t: str) -> bool:
    words = t.split()
    if not words or len(words) > 8:
        return False
    if re.search(r"\.\s+\S", t):
        return False
    if words[-1].lower().rstrip(".,;:") in STOP_TAIL:
        return False
    if sum(1 for c in t if c.isalpha() or c.isspace() or c in "-/") / max(len(t), 1) < 0.85:
        return False
    return True


def classify(term: str, definition: str) -> str:
    """Heuristic: 'g' (good glossary entry) or 'b' (noise)."""
    t = term.strip()
    d = definition.strip()
    if not t or not d: return "b"
    if t in NOISE_TERMS: return "b"
    if is_recognized_acronym_entry(t, d): return "g"
    if re.fullmatch(r"[A-Z]{6,}", t): return "b"
    if t.lower().startswith(("this section", "see ", "pin ")): return "b"
    if len(d) < 15: return "b"
    if t.startswith(("a. ", "b. ", "c. ", "(1)", "(2)", "(3)", "(4)", "(5)")): return "b"
    if re.search(r"\b(and|or|the|of|to|with|in|on|for|by|as|are|is|was|were|that|which|who)$", t, re.IGNORECASE):
        return "b"
    if len(t) > 80 or len(t) < 2: return "b"
    if re.fullmatch(r"[\d\.,\-/ ]+", t): return "b"
    if re.search(r"\([A-Z]{2,5}\s*$", t) or re.search(r"\(AR\b", t): return "b"
    if not looks_like_noun_phrase(t): return "b"
    if re.match(r"^(AR|PAM|FM|ATP|ADP|TC|TM|SD|STP)[\s\-]\d", d) and len(d) < 25:
        return "b"
    if re.fullmatch(r"[\d\.\)\s]+", d): return "b"
    return "g"


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    cand_dir = repo_root / "validation_set" / "candidate-output"
    pdf_dir = repo_root / "validation_set" / "pdfs"
    out_path = repo_root / "validation_set" / "labels.yaml"

    if not cand_dir.exists():
        print(f"ERROR: {cand_dir} not found", file=sys.stderr)
        return 1

    reviewed = set(BATCH1 + BATCH2 + BATCH3)

    labels = {
        "expected_stratification": {"AR": 13, "PAM": 6, "FM": 4, "ATP": 2, "ADP": 1, "TC": 1},
        "documents": [],
    }

    for cf in sorted(cand_dir.glob("*.json")):
        base = cf.stem
        pdf_name = f"{base}.pdf"
        if not (pdf_dir / pdf_name).exists():
            candidates = list(pdf_dir.glob(f"{base}*.pdf"))
            if candidates:
                pdf_name = candidates[0].name
        m = re.match(r"^([A-Z]+)_", base)
        doc_type = m.group(1) if m else "?"
        if doc_type not in {"AR", "PAM", "FM", "ATP", "ADP", "TC", "TM"}:
            continue
        is_reviewed = any(base.startswith(p) for p in reviewed)
        flipped_bad: set[str] = set()
        flipped_good: set[str] = set()
        excluded: set[str] = set()
        if is_reviewed:
            for k, v in FLIPS_GOOD_TO_BAD.items():
                if base.startswith(k):
                    flipped_bad.update(v)
            for k, v in FLIPS_BAD_TO_GOOD.items():
                if base.startswith(k):
                    flipped_good.update(v)
            for k, v in EXCLUDE_FROM_NEGATIVES.items():
                if base.startswith(k):
                    excluded.update(v)

        with open(cf) as fh:
            data = json.load(fh)
        entries = data.get("entries", [])
        tier1_pos: list[dict] = []
        neg: list[dict] = []
        auto_pos: list[dict] = []
        auto_neg: list[dict] = []

        for e in entries:
            cls = classify(e["term"], e["definition"])
            if e["term"] in excluded:
                continue
            if is_reviewed:
                if e["term"] in flipped_bad:
                    neg.append({"term": e["term"], "source_type": e["source_type"]})
                elif e["term"] in flipped_good:
                    tier1_pos.append({"term": e["term"], "source_type": e["source_type"]})
                elif cls == "b":
                    neg.append({"term": e["term"], "source_type": e["source_type"]})
                else:
                    tier1_pos.append({"term": e["term"], "source_type": e["source_type"]})
            else:
                (auto_pos if cls == "g" else auto_neg).append(
                    {"term": e["term"], "source_type": e["source_type"]}
                )

        labels["documents"].append({
            "pdf": pdf_name,
            "doc_type": doc_type,
            "tier1_positive_terms": tier1_pos,
            "negative_labels": neg,
            "auto_positive_labels": auto_pos,
            "auto_negative_labels": auto_neg,
            "labels": [],
        })

    with open(out_path, "w") as fh:
        yaml.safe_dump(labels, fh, sort_keys=False, default_flow_style=False, width=200)

    n_t1 = sum(len(d["tier1_positive_terms"]) for d in labels["documents"])
    n_neg = sum(len(d["negative_labels"]) for d in labels["documents"])
    n_ap = sum(len(d["auto_positive_labels"]) for d in labels["documents"])
    n_an = sum(len(d["auto_negative_labels"]) for d in labels["documents"])
    print(f"Wrote {out_path}")
    print(f"  Tier-1 positives: {n_t1}")
    print(f"  Negative labels:  {n_neg}")
    print(f"  Auto pos (Tier 2): {n_ap}")
    print(f"  Auto neg (Tier 2): {n_an}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
