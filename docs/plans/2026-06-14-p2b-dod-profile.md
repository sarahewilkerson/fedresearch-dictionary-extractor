# P2-B — DoD/Joint extraction profile (dictionary-extractor v0.6.0)

**Date:** 2026-06-14 · **Status:** APPROVED (rev 3, post-Codex iter-1+iter-2; iter-3 operator-judgment) · **Repo:** fedresearch-dictionary-extractor · **Parent:** backend audit F1 / P2-B; scoping `fedresearch:docs/plans/2026-06-13-dict-p2-extraction-profiles-scoping.md` (narrowed Army+DoD-only 2026-06-14); U0 sampling `fedresearch:docs/plans/2026-06-14-dict-p2u0-glossary-sampling.md`.

## Phase 0.a Classification
**full-flow** — new integration boundary (new extractor profile) + socratic design for the term-gating strategy. Pass-2 context check: likely-touched = `profiles/dod.py` (new), `profiles/__init__.py`, `profiles/base.py`, `extractors/glossary.py`, `core/analyzer.py`, `validation_set/*`, `tests/*`, `scripts/*`, `pyproject.toml`, `CHANGELOG.md`, `README.md`. `glossary.py`+`analyzer.py` are the shared Army-critical parse path → full-gate rigor.

## 1. Problem statement
The dictionary covers Army only (`profiles/army.py` is the sole profile). Operator scope is now **Army + DoD**. Add a **DoD/Joint** profile so DoD-wide issuances (DoDI/DoDD/DoDM/AI/DTM/DoD CPM) and Joint docs (CJCS Instruction/Manual/Notice/Guide, Joint Publication — folded into DoD) extract glossary definitions. Output: released wheel **v0.6.0** with a `dod` profile, validated against a hand-labelled, **reproducible** DoD doc set, SHA256 captured for the Phase-C backend pin. Army behavior must be **provably unchanged** (deterministic golden equality). **Scope caveat (Codex iter-2):** DoD issuances (DoDI/DoDD/DoDM/AI/DTM/DoD CPM) are the required-pass families; Joint (CJCS*/JP) is targeted and per-family gated — the shipped v0.6.0 claim (§2a) matches exactly which families passed (Joint marked experimental if any fail).

## 2. Assumptions & alternatives considered
- **A1 (VERIFIED, planning):** DoD glossary = back-matter `GLOSSARY` with `PART I. ABBREVIATIONS AND ACRONYMS` then `PART II. DEFINITIONS`; entries `Term.  Definition`. Evidence: DODI 3150.09 pages 32-36 (`BSA.  Defined in Reference (k).`, `CBR hardness.  The capability…`, `DODIN.  The globally interconnected…`). TOC dot-leader refs (page 4) skipped by range-detection largest-block + later tie-break — but see A6 (must be hardened).
- **A2 (VERIFIED, planning) — the hard-30%, resolved:** DoD definition pages are fully left-justified (x=72 for term AND continuation) with NO bold (OCR'd). Army's bold-gate → ≈0 entries; X-only fallback → over-segmentation. Discriminator is textual: new term = line matching the split pattern `^Term.  <Capital>`; continuations start lowercase/mid-sentence. → new profile property **`term_gate_mode="inline_split"`** (Army default `"spatial"`).
- **A3 (Codex-1) — analyzer fallback must be neutralized for DoD:** `core/analyzer.py:111` reruns `parse_glossary_entries(force_legacy_gate=True)` when `profile.enable_bold_gate AND _bold_preservation_rate<0.10`. DoD is no-bold → this WOULD fire and could replace good `inline_split` output with over-segmented X-only output. **Mitigation (two locks):** (a) DoD sets `enable_bold_gate=False` → the `and` short-circuits, fallback never runs (VERIFY: grep confirms analyzer.py:111 is the ONLY `_bold_preservation_rate`/`force_legacy_gate` trigger); (b) the `inline_split` branch in `parse_glossary_entries` ignores `force_legacy_gate` entirely (textual gate, not X-position). **Both** + an e2e `analyze_pdf(profile="dod")` test asserting `metadata.glossary_used_legacy_fallback is False` and correct entries.
- **A4 (Codex-6) — split pattern is profile-overridable, not a shared mutation:** add a profile property `inline_split_pattern` (default = the current Army `split_re` source); DoD supplies its own ONLY if corpus characterization (step 1) shows DoD term separators / first-def chars / term char-sets diverge from the Army regex. **The shared `split_re` literal is NOT mutated** (Army-safe). Characterization inventories: separator inventory (`.  ` vs `  ` vs `—`), first-def-char distribution, term char-set (digits/dots/slashes/parens).
- **A5 (Codex-4):** PART I acronyms (`AEP  Alternate…`) ALSO parse under `inline_split` (whitespace-sep branch) — consistent with Army Section-I (v0.5 D-3-A). Section headers (`PART I.  ABBREVIATIONS…`, `PART II.  DEFINITIONS`, bare `GLOSSARY`, intro sentence) rejected via `invalid_term_patterns`. **False positives** (`U.S.  Forces…`, `Reference (k).  The…`, capitalized continuation fragments) are the real risk → see Verification precision floor + negative continuation corpus.
- **A6 (Codex-3) — range detection hardened for DoD:** `GLOSSARY` is broad (TOC, running headers, appendix labels). Beyond largest-block+later tie-break, add a **DoD content-confirmation**: the selected block must contain at least one of `PART I`, `PART II`, `ABBREVIATIONS`, `DEFINITIONS` on a body (non-dot-leader) line; else reject/continue. Implemented as a DoD-profile-gated post-check (Army path untouched). Negative range fixtures required (see Verification).
- **A7 (Codex-5):** CJCS/JP are acceptance-gated per family, not folded under a single DoDI threshold. A family whose fixtures fail its floor is EITHER fixed OR explicitly marked **experimental** in CHANGELOG with the documented gap — never silently shipped as "covered".
- **A8 (Codex-7):** `_guess_doc_type` takes the first pub-number token → wrong for `DoD CPM Issuance`/`Joint Publication`. DoD `publication_patterns` + a doc-type derivation that yields correct canonical types for DoDI/DoDD/DoDM/AI/DTM/DoD CPM/CJCSI/CJCSM/CJCSN/JP; covered by filename→(pub_number,doc_type) fixtures per family.
- **A9 (Codex-8) — reproducible corpus:** commit `validation_set/dod-corpus-manifest.yaml` (per doc: gcs_key, sha256, page_count, family, glossary_page_range, fixture filenames+checksums). **Labeling methodology:** for a **core subset** (DODI 3150.09 + ≥1 per family) do **full-glossary labeling** (every expected term) → true precision/recall; for the remainder use **sentinel-term** labeling (must-find terms) + the negative continuation corpus for the FP audit. The metric name reflects the method (no "precision/recall" claim on sentinel-only docs).
- **Alternatives rejected:** `enable_bold_gate=False`/X-only as the DoD gate (A2: over-segments); DoD Section-II narrowing analog (deferred — PART I acronyms are wanted, headers rejected); mutating shared `split_re` (A4: Army-unsafe).

## 2a. Acceptance thresholds & family matrix (Codex iter-2)
**Numeric gates (defined now; the *achieved* numbers are recorded in execution):**
- **Per-family recall floor:** ≥ 0.85 of labelled expected terms on each FULL-labelled doc.
- **Per-doc false-positive cap:** ≤ 2 emitted terms not in the labelled set (full-labelled docs), and **0** header/section-marker-as-term, on EVERY validation doc.
- **Sentinel docs:** 100% of sentinel terms found (0 missing) + FP audit against the negative continuation corpus.
- **Emitted-term review (Codex iter-2):** for the core full-labelled doc per family AND every high-risk family (CJCS, JP), EVERY emitted term is reviewed (not just negative-corpus matches) — precision is computed from this review, not inferred.
- **xfail rule:** a family that cannot meet its floor ships as an explicit `@pytest.mark.xfail(reason=...)` with the gap documented in CHANGELOG + the family matrix; it does NOT silently pass and the release claim is narrowed accordingly.

**Family matrix — every claimed family gets ≥1 real fixture + a status (filled in execution):**

| Family | Doc types | Fixtures (≥) | Status (pass / xfail-experimental) |
|---|---|---|---|
| DoDI | DoD Instruction | 1 full + sentinels | required pass |
| DoDD | DoD Directive | 1 | required pass |
| DoDM | DoD Manual | 1 | required pass |
| AI | Administrative Instruction | 1 | required pass |
| DTM | Directive-Type Memorandum | 1 | required pass |
| DoD CPM | DoD CPM Issuance | 1 | required pass |
| CJCSI | CJCS Instruction | 1 | pass or xfail-experimental |
| CJCSM | CJCS Manual | 1 | pass or xfail-experimental |
| CJCSN | CJCS Notice | 1 | pass or xfail-experimental |
| CJCS Guide | CJCS Guide | 1 | pass or xfail-experimental |
| JP | Joint Publication | 1 | pass or xfail-experimental |

**Release-claim scoping (Codex iter-2):** v0.6.0 CHANGELOG/README claim is **"DoD issuances (DoDI/DoDD/DoDM/AI/DTM/DoD CPM) supported; Joint (CJCS*/JP) <supported|experimental>"** — the word chosen from the matrix's actual status. Problem statement §1 is read with this caveat: Joint is *targeted*, gated per-family, and the shipped claim matches what passed.

## 3. Root cause analysis
N/A (feature). Design-constraint RCA: DoD issuance PDFs are left-justified, OCR'd, no-bold → spatial gating is structurally inapplicable; textual gating is the correct model.

## 4. Approach & methodology
1. **Build a reproducible validation corpus first** (de-risks A3/A5/A6/A7/A8). Pull 10-12 DoD PDFs from `gs://fr-docs-prod` (Hetzner→scp `validation_set/pdfs/`, gitignored): DoDI/DoDD/DoDM/AI/DTM + DoD CPM, ≥2 CJCS (Instruction+Manual), ≥1 JP, incl. DODI 3150.09. For each: record gcs_key/sha256/page_count/family in the manifest; dump glossary region (text + span x/bold); inventory separators/first-def-char/term-charset; confirm `inline_split` applies and note bold/indent outliers.
2. **TDD the gate (synthetic unit tests)** — `inline_split` line classification (new-term/continuation/header/acronym) + false-positive guards (`U.S. Forces`, `Reference (k).`, capitalized continuation). RED→GREEN.
3. **base.py** — add `term_gate_mode` (default `"spatial"`) + `inline_split_pattern` (default Army regex). **glossary.py** — additive `inline_split` branch (ignores `force_legacy_gate`). **analyzer.py** — confirm `enable_bold_gate=False` neutralizes the fallback (no code change if grep confirms; else gate it on `term_gate_mode`).
4. **profiles/dod.py** + register `"dod"`; DoD content-confirmation hook for range detection.
5. **Capture fixtures** (range text JSON + parser dict JSON) + negative range fixtures; capture script under `scripts/`.
6. **Hand-label** `validation_set/labels-dod.yaml` (per A9 methodology) + corpus manifest + golden tests (per-family gates, precision floor, negative continuation corpus, pub-number/doc-type fixtures).
7. **Army no-drift:** capture deterministic golden JSON for ≥3 representative Army fixtures BEFORE the parser edit; assert byte-identical after. Plus full suite green.
8. **Release** v0.6.0: bump version, CHANGELOG (incl. per-family results + any experimental gaps), README; `python -m build`; `gh release create v0.6.0 dist/*.whl`; capture SHA256.

## 5. The hard 30%
- **(RESOLVED, high) gating** — `inline_split` via overridable split pattern. Residual = generalization (A7).
- **(Codex-1, mitigated) analyzer fallback override** — neutralized by `enable_bold_gate=False` + inline_split ignoring `force_legacy_gate` + e2e assertion. Confidence high once grep+e2e confirm.
- **(MED) inline_split false positives** — precision floor + per-doc FP cap + negative continuation corpus.
- **(MED) range detection on `GLOSSARY`** — content-confirmation + negative fixtures.
- **(MED) CJCS/JP divergence** — per-family gates; experimental-marking escape hatch.
- **(MED) split-pattern divergence** — characterized in step 1; profile-override available.
- **(LOW) multi-token doc-type derivation** — per-family pub-number fixtures.

## 6. Blast radius
- **`extractors/glossary.py`** + **`core/analyzer.py`** — shared Army-critical path. Changes are additive and reached only for `term_gate_mode=="inline_split"` / `enable_bold_gate=False`. **Guarded by deterministic Army golden equality (≥3 fixtures) + full suite.**
- **`profiles/base.py`** — two additive non-abstract properties with safe defaults (existing pattern). No existing profile breaks.
- **`profiles/__init__.py`** — additive registry entry.
- New files only otherwise. Version bump/release inert until Phase C pins the wheel.

## 7. Verification strategy
- **Unit (gate):** `pytest tests/test_dod_inline_split_gate.py` — new-term/continuation/header/acronym classification + explicit false-positive cases (`U.S.  Forces…`, `Reference (k).  The…`, capitalized continuation) asserted NOT to emit terms.
- **Range (positive + negative, tightened — Codex iter-2):** `pytest tests/test_dod_glossary_range.py` — DODI 3150.09 → (32,36) 0-idx; content-confirmation requires (a) **ordered** markers (`PART I`/`ABBREVIATIONS` appears before `PART II`/`DEFINITIONS` when both present, OR `DEFINITIONS` present), (b) **≥3 parseable `inline_split` entries** in the selected block, (c) termination scanned to occur before a post-glossary references/appendix section. Negative fixtures that must be REJECTED: TOC-only `GLOSSARY`, multi-page TOC refs, one-page glossary reference, running-header-only matches, appendix-after-glossary.
- **Parser (real dict fixtures):** `pytest tests/test_dod_parser_fixtures.py` — expected terms emitted (`CBR hardness`, `DODIN`, `materiel developer`, `BSA`, …); NO continuation fragments; NO header-as-term.
- **e2e analyzer (Codex-1):** `pytest tests/test_dod_analyze_pdf.py` — `analyze_pdf(path, profile_name="dod")` on a captured fixture: `metadata.glossary_used_legacy_fallback is False`, entry set matches expected, no oversegmentation (entry count within tolerance of labelled).
- **Validation golden (per-family, Codex-5):** `pytest -m validation tests/test_dod_validation.py` — per-family recall floor (core full-labeled docs) + sentinel-hit for the rest; **precision floor / per-doc FP cap** measured against the negative continuation corpus; zero header-as-term. Any family below floor → CHANGELOG experimental note (test xfails with documented reason, not silent pass).
- **Pub-number/doc-type (Codex-7):** `pytest tests/test_dod_pub_number.py` — filename→(source_pub_number, source_doc_type) for DoDI/DoDD/DoDM/AI/DTM/DoD CPM/CJCSI/CJCSM/CJCSN/JP, incl. multi-token families.
- **Army no-drift (Codex-2):** capture `analyze_pdf(army_fixture, deterministic=True)` JSON for ≥3 representative Army docs (varied: Section I/II, bold, OCR-fallback) BEFORE the edit; `pytest tests/test_army_no_drift.py` asserts byte-identical JSON after. Plus full default suite green.
- **Reproducibility (Codex-8 + iter-2):** `validation_set/dod-corpus-manifest.yaml` committed; `scripts/fetch_dod_corpus.py` re-fetches PDFs from the manifest's GCS keys (asserting SHA256) and `scripts/build_dod_fixtures.py` regenerates the committed range/parser fixtures deterministically. A test asserts each committed fixture's checksum matches the manifest. **CI policy:** PDF-dependent tests (validation golden) are marked `@pytest.mark.requires_pdf` and **skip** when `validation_set/pdfs/` is absent (CI default), so the committed-fixture tests (range/parser/e2e — PDF-free) are the CI gate; the validation golden runs locally where PDFs are fetched.
- **Release (Codex iter-2 — functional, not just version):** `gh release view v0.6.0` shows `.whl`; SHA256 captured; **clean-venv smoke test**: `pip install` the wheel, then `extract-definitions --input <committed sample PDF or fixture-backed path> --profile dod --output /tmp/out.json` → asserts expected glossary entries present AND `glossary_used_legacy_fallback==False` (not merely `--version`).

## 8. Documentation impact
- `CHANGELOG.md` — `[0.6.0]` Added (dod profile, inline_split mode, range content-confirmation), the gating RCA, **per-family validation results + any experimental gaps**.
- `README.md` — add `dod` to profile/`--profile` list.
- `validation_set/README.md` — DoD label set + manifest + labeling methodology.

## 9. Completion criteria
- [ ] `get_profile("dod")` works; `"dod"` in PROFILES.
- [ ] `term_gate_mode` + `inline_split_pattern` in base.py (defaults preserve Army); additive `inline_split` branch in glossary.py; analyzer fallback neutralized for DoD (grep-confirmed + e2e-asserted).
- [ ] All new suites pass; **Army deterministic golden JSON byte-identical** to the step-2 pre-edit committed baseline (≥3 fixtures); full suite green.
- [ ] §2a family matrix filled: DoDI/DoDD/DoDM/AI/DTM/DoD CPM required-pass meet recall floor; CJCS*/JP pass OR xfail-experimental with documented gap; release claim scoped to match.
- [ ] §2a numeric thresholds met: recall ≥0.85/family, ≤2 FP/doc, 0 missing sentinels, 0 header-as-term; emitted-term review done for core+CJCS+JP.
- [ ] `validation_set/labels-dod.yaml` + `dod-corpus-manifest.yaml` + `scripts/fetch_dod_corpus.py` + `scripts/build_dod_fixtures.py` committed; PDFs gitignored; PDF-dependent tests `requires_pdf`-skip in CI.
- [ ] Pub-number/doc-type fixtures pass for ALL matrix families (incl. multi-token DoD CPM / Joint Publication).
- [ ] Wheel **v0.6.0** released; clean-venv `--profile dod` functional smoke test passes; **SHA256 recorded** in worklog (Phase C).
- [ ] `/review-execution` Codex gate CLEAN; merged to extractor `main`.

## 10. Execution sequence
1. **Worklog + reproducible corpus + fetch script.** Download 10-12 DoD/Joint PDFs (one per family in the matrix); build `dod-corpus-manifest.yaml` (gcs_key/sha256/page_count/family) + `scripts/fetch_dod_corpus.py`; dump glossary regions; inventory separators/first-def-char/term-charset; characterize per family incl. CJCS+JP. *Verify:* `ls validation_set/pdfs/*.pdf|wc -l`≥10; manifest committed; `python scripts/fetch_dod_corpus.py --dry-run` lists all keys; worklog has per-family separator/charset inventory. *Rollback:* `rm` (gitignored) / `git checkout -- validation_set/ scripts/`.
2. **Army baseline capture (FIRST-CLASS pre-edit step — Codex iter-2).** BEFORE any `glossary.py`/`analyzer.py` edit, on clean current `main` behavior, capture `analyze_pdf(army_fixture, deterministic=True)` golden JSON for ≥3 representative Army docs (Section I/II, bold, OCR-fallback) into `tests/fixtures/army_no_drift/` and COMMIT. *Verify:* `git show HEAD --stat` lists the committed golden files; they were generated on un-edited parser code (commit precedes step 4). *Rollback:* `git checkout -- tests/fixtures/army_no_drift/`.
3. **RED gate + FP unit tests.** `tests/test_dod_inline_split_gate.py` incl. false-positive cases, against not-yet-existing properties. *Verify:* `pytest tests/test_dod_inline_split_gate.py` FAILS (attr error). *Rollback:* `git checkout -- tests/`.
4. **GREEN: base.py + glossary.py + analyzer confirm.** Add `term_gate_mode`+`inline_split_pattern`; additive `inline_split` branch (ignores `force_legacy_gate`); grep-confirm analyzer fallback gating. *Verify:* gate+FP tests pass; **`pytest tests/test_army_no_drift.py` byte-identical to the step-2 committed golden**; full suite green. *Rollback:* revert the 2-3 files (defaults restore Army).
5. **DodProfile + register + range content-confirmation.** `profiles/dod.py` (incl. `publication_patterns` + doc-type derivation for all matrix families); PROFILES entry; DoD-gated ordered+entry-count range confirmation hook. *Verify:* `get_profile('dod')`; range positive+negative tests pass. *Rollback:* `git checkout -- profiles/ extractors/`.
6. **Capture fixtures + regen script + range/parser/e2e tests.** `scripts/build_dod_fixtures.py` → range+parser+negative fixtures; `test_dod_glossary_range.py`, `test_dod_parser_fixtures.py`, `test_dod_analyze_pdf.py`. *Verify:* all pass; DODI 3150.09 range==(32,36); `glossary_used_legacy_fallback is False`. *Rollback:* `git checkout -- tests/ scripts/`.
7. **Hand-label + per-family golden + emitted-term review + pub-number tests.** `labels-dod.yaml` (full-labelled core per family + sentinels); validation golden with the §2a numeric thresholds, emitted-term review for core+CJCS+JP, negative continuation corpus; `test_dod_pub_number.py` (all matrix families incl. multi-token DoD CPM/JP). Fill the §2a family-matrix status column. *Verify:* `pytest -m validation` meets the numeric floors or `xfail`s experimental families with documented reason; pub-number tests pass for every matrix family. *Rollback:* `git checkout -- validation_set/ tests/`.
8. **Full regression.** *Verify:* `pytest` all green; `test_army_no_drift.py` byte-identical. *Rollback:* gate.
9. **Release v0.6.0.** Bump version, CHANGELOG (per-family matrix results + scoped claim + gaps), README (scoped claim); `python -m build`; `gh release create v0.6.0 dist/*.whl`; capture SHA256. *Verify:* `gh release view v0.6.0` lists `.whl`; **clean-venv smoke test** `extract-definitions --profile dod` on a sample → expected entries + `glossary_used_legacy_fallback==False`. *Rollback:* `gh release delete v0.6.0`+`git tag -d v0.6.0`.

## 11. Do Not Touch
- **`profiles/army.py`** — zero edits.
- **The `"spatial"` gate path** in `parse_glossary_entries` (bold-gate/X-only). The `inline_split` branch is strictly additive.
- **The shared `split_re` literal** — NOT mutated. DoD divergence is handled via the `inline_split_pattern` profile override (default = current Army regex).
- **`narrow_to_section_ii` / `detect_section_structure`** — Army machinery (UNKNOWN for non-army); leave as-is.
- **Existing fixtures + Army validation YAMLs** — no edits (would mask regressions); Army no-drift uses NEW captured golden fixtures.
- **Backend repo** — Dockerfile pin + EXTRACTOR_VERSION are Phase C.

## Execution Checklist (handoff contract for /develop Phase 5)
- [ ] 1. Worklog + corpus (10-12 PDFs, one/family) + `dod-corpus-manifest.yaml` + `scripts/fetch_dod_corpus.py`; separator/charset inventory.
- [ ] 2. **Army baseline** golden JSON (≥3 fixtures) captured on clean code + committed (PRE-edit).
- [ ] 3. RED `test_dod_inline_split_gate.py` (incl. FP cases) — fails on missing properties.
- [ ] 4. GREEN: base.py (`term_gate_mode`,`inline_split_pattern`) + glossary.py additive branch + analyzer fallback grep-confirm; gate+FP+Army-no-drift green.
- [ ] 5. `profiles/dod.py` (+ pub-number/doc-type for all families) + register + ordered/entry-count range confirmation.
- [ ] 6. `scripts/build_dod_fixtures.py` + range/parser/e2e tests (DODI 3150.09 range==(32,36); no legacy fallback).
- [ ] 7. `labels-dod.yaml` + per-family golden (§2a thresholds) + emitted-term review + negative continuation corpus + `test_dod_pub_number.py`; fill family-matrix status.
- [ ] 8. Full `pytest` green; Army no-drift byte-identical.
- [ ] 9. Release v0.6.0 (version+CHANGELOG+README scoped claim); build wheel; `gh release create`; clean-venv `--profile dod` smoke test; **record SHA256**.
- [ ] Docs: CHANGELOG [0.6.0] + README profile list + validation_set/README.

## Plan-Review Record
- Iter-1 Codex (0 SUCCESS): 8 structural findings → all incorporated (rev 2).
- Iter-2 Codex (0 SUCCESS): 8 refinement findings → all incorporated (rev 3).
- Iter-3: APPROVED via operator-judgment (stable design across both rounds; all fixes bounded targeted edits; converging — structural→granularity).
