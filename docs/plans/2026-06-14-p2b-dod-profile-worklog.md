# P2-B DoD profile — worklog

## Planning evidence (pre-execution)
- **Architecture read:** profiles/base.py (interface), cli.py (`--profile` dispatch), profiles/__init__.py (PROFILES registry), core/analyzer.py (orchestration + bold-preservation fallback at :111), extractors/glossary.py (`find_glossary_page_range` :181 largest-block+later tie-break; `parse_glossary_entries` :433 + `split_re` :469 handles `Term. Definition`; `detect_section_structure` :303 returns UNKNOWN for non-army).
- **DoD format characterized (DODI 3150.09, GCS):** glossary pages 32-36 (0-idx); PART I. ABBREVIATIONS/ACRONYMS (32-33) + PART II. DEFINITIONS (34-36). Entries `Term.  Definition`: `BSA.  Defined in Reference (k).`, `CBR hardness.  The capability…`, `DODIN.  …`, `materiel developer.  …`. TOC dot-leader refs page 4.
- **Hard-30% resolved (span dump):** definition pages fully left-justified x=72 (term AND continuation) + NO bold (flags=4 OCR). → both Army gates fail → new `inline_split` textual gate via split_re.
- **Corpus access verified:** `gs://fr-docs-prod` via Hetzner gcloud SA → scp local works (DODI 3150.09 downloaded 834KB).
- **Release process:** version in pyproject.toml + __init__.py; CHANGELOG; CI `python -m build` + SHA-256; `gh release create vX.Y.Z` with `.whl` asset; SHA via `gh release view --jq '…digest'`.

## Plan review
- Iter-1 Codex 0 SUCCESS: 8 structural findings (analyzer fallback override, Army golden equality, range content-confirmation, FP strategy, CJCS/JP gating, split-pattern override, multi-token doc-type, corpus manifest) → all incorporated rev 2.
- Iter-2 Codex 0 SUCCESS: 8 refinement findings (family matrix, numeric thresholds, emitted-term review, fetch/regen script + CI policy, first-class Army baseline, scope claim, tighter range, dod smoke test) → all incorporated rev 3.
- Iter-3: APPROVED operator-judgment (stable design; bounded fixes; converging structural→granularity).

## Execution increments
(pending)
