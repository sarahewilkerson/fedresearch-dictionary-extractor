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

### Step 2 — Army no-drift baseline (DONE)
- Captured `parse_glossary_entries(ARMY)` golden on the 3 committed parser fixtures, on un-edited code, committed BEFORE any glossary.py edit (`tests/test_army_no_drift.py` + `tests/fixtures/army_no_drift/`). Asserts byte-identical after.

### Steps 3-4 — inline_split gate (TDD, DONE)
- base.py: `term_gate_mode` (default "spatial") + `inline_split_pattern` (default None=reuse split_re). glossary.py: additive inline_split branch. 7 RED→GREEN gate tests; full suite 277 passed; Army no-drift byte-identical. analyzer.py NOT changed (DoD enable_bold_gate=False short-circuits the fallback — grep-confirmed analyzer.py:112 is the only trigger).

### Step 5 — DodProfile + precision (DONE)
- profiles/dod.py + registered "dod". Real DODI 3150.09 run: 36→35 entries.
- Precision fixes (inline_split branch only): leading function-word rejection (kills "the assigned mission" wrapped-continuation FP); header/footer-zone guard on continuations (kills "Change 4, 12/08/2023 GLOSSARY" running-header bleed).

### Step 6 — range content-confirmation (DONE)
- confirm_glossary_block hook (base default True=Army unchanged); find_glossary_page_range picks largest CONFIRMED block. DoD confirm = ≥3 term.def lines AND ≤2 dot-leaders. Fixed AI_31 (was extracting a TOC signature "William E" → now its real page-10 glossary, 9 entries). FP cleanup: G.1/G.2 enclosure labels, bare U.S/U.S.C, signatures, PART-Il OCR variant.

### Step 7 — tests + repro (DONE)
- test_dod_inline_split_gate (9), test_dod_parser_fixtures (committed DODI fixture, PDF-free CI gate), test_dod_pub_number (11, incl. multi-token), test_dod_validation (20, @validation — corpus floors + e2e no-fallback + sha256 manifest). scripts/fetch_dod_corpus.py + build_dod_fixtures.py. Default suite 289 passed; -m validation 20 passed.

### Step 8 — full regression (DONE)
- `pytest` 289 passed / 0 failed; Army no-drift byte-identical.

### Step 9 — release prep (DONE pre-publish)
- version → 0.6.0 (pyproject + __init__). CHANGELOG [0.6.0] with family matrix + scoped claim. README + profile list.
- `python -m build` → fedresearch_dictionary_extractor-0.6.0-py3-none-any.whl. Clean-venv smoke test: install + `--version`==0.6.0 + `--profile dod` on DODI 3150.09 → 35 entries, no legacy fallback. PASS.
- **Per-family matrix (achieved):** REQUIRED-PASS — DoDI(35), DoDM(63), DoDCPM(22), AI(9), DoDD(4), DoDI-3305(4), DTM(4). EXPERIMENTAL — CJCSI(1), CJCSM(6), CJCSN(0), CJCS Guide(61 noisy), JP(8). Release claim: DoD issuances supported; Joint experimental.
- **GitHub release publish + SHA256 capture: PENDING /review-execution CLEAN + operator OK** (outward-facing publish).

### Discovered/deferred
- `validation_set/pdfs` committed broken self-referential symlink (worked around with dod_pdfs/). Separate cleanup PR.
- Residual inline_split FPs (~1-2/doc, e.g. "surrounding medium") — inherent to textual gating; within the ≤2/doc cap; measured in validation.
