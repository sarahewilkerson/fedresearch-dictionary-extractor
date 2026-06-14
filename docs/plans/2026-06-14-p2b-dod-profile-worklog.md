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

### Step 1 — corpus + characterization (DONE)
- 12 PDFs (one per family) pulled from `gs://fr-docs-prod` via Hetzner → local `validation_set/dod_pdfs/` (gitignored; added to `.gitignore`). `validation_set/dod-corpus-manifest.yaml` committed (gcs_key/pages/sha256/family/glossary_class).
- **DISCOVERED repo bug (deferred, NOT mine to fix here):** `validation_set/pdfs` is a committed **self-referential (broken circular) symlink** (`pdfs -> .../validation_set/pdfs`). Could not write through it (`Too many levels of symbolic links`). Worked around by using `validation_set/dod_pdfs/`. Flag for a separate cleanup PR (it also likely breaks Army `build-text-fixtures.py` paths on a fresh clone).
- **Characterization finding (validates Codex iter-2 #5 + the family-matrix design):** the corpus splits into structural classes:
  - **Class 1 — clean back-matter `Term.  Definition`** (inline_split target, HIGH confidence): **AI** (`AEP. A program…`), **DODI** 3150.09 + 3305.14 (`JIT. Individual…`, `certification.  Defined in Reference (c).`), **DoD CPM** (`award.  A monetary…`), **DODD** (`G.2. DEFINITIONS.` bold header, defs indented x=200), **DODM** (`EDI . The…`, BOLD terms x=72). → **required-pass families**. Note DODD/DODM preserve bold (boldrate 0.25-0.26); DODI/AI/DoDCPM are no-bold x=72 (the DODI 3150.09 case). inline_split (textual) handles both.
  - **Class 2 — inline numbered/lettered "Definitions" paragraph** (NOT back-matter glossary): **CJCSI** (`5. Definitions.`), **CJCSM** (`b. Definitions` / `(1) Port Handling. …`), **CJCSN** (`5. Definitions.`). Definitions embedded in body prose → range-detection won't find a clean block → **xfail-experimental** for v0.6.0.
  - **CJCS Guide** — TOC-shadowed, glossary unclear → experimental.
  - **JP** (`JP_1-04`) — HAS back-matter `GLOSSARY / PART I—ABBREVIATIONS … / PART II` but **two-column / term-and-def-on-separate-lines** layout (`AOR`\n`area of responsibility`) → inline_split single-line assumption may not hold → **experimental** until validated.
- **Implication for the family matrix (§2a):** required-pass DoD-issuance families (DoDI/DoDD/DoDM/AI/DoD CPM) are Class 1 → expected pass. DTM needs a glossary-presence check. CJCS* + JP are Class 2/3 → expected **xfail-experimental**; v0.6.0 release claim = "DoD issuances supported; Joint/CJCS experimental." This matches the plan's escape hatch exactly.

### Steps 2-9 — PENDING (handed off; see status report)
