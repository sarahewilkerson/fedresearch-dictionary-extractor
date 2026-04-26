# Changelog

## [0.2.0] — 2026-04-26

Release of the v0.2.0 wheel after the 6-unit decomposition that resolved Unit 1's escalated planning. See `docs/plans/2026-04-26-v0.2-decomposition.md` for the meta-plan.

### Added
- **Section header detection** (Unit 2): `metadata.section_structure` ∈ {`none`, `section_i_only`, `section_ii_only`, `both`, `unknown`}. Profile-gated to Army; OCR-tolerant regex matches `Section II` and `Section Il` only (production-observed forms). Detection-only — no extraction-behavior change.
- **Section II range scoping** (Unit 3): when `section_structure ∈ {both, section_ii_only}`, `find_glossary_page_range` is narrowed to the Section II range, ending at the first Section III/IV/V/VI/VII header or the original glossary end. Bold-fallback path also uses the narrowed range.
- 4 new optional `Metadata` fields (Unit 3): `section_ii_pages`, `section_ii_narrowing_attempted`, `section_ii_narrowing_fired`, `section_ii_boundary_scan_errors`. Schema is back-compat (additive).
- 4 new validation PDFs (Unit 4): AR 380-381, AR 637-2, AR 115-10, AR 700-13 (Section-I-heavy worst-offender docs from the 2026-04-25 100-doc backfill).
- `validation_set/labels-batch2-section-i.yaml` + `.manifest.json` (Unit 4): bug-pattern annotations + provenance for the 4 new docs.
- `validation_set/manifest_audit.md` (Sub-Unit 1a): canonical corpus state.
- `validation_set/batch1_reconciled.yaml` + `tests/test_batch1_reconciled.py` (Sub-Unit 1b): hand-vetted forbidden-pair corpus pin.
- `validation_set/v0.2.0_classifier_snapshot_diff.md` (Unit 5): documented diff between prefix and current classifier snapshots — 47 removed (Unit 3 narrowing), 199 added (Unit 4 new docs), 12 b→g flips (matches existing fixture), 0 g→b regressions.
- `scripts/measure_section_distribution.py` (Unit 3): operator-run distribution analysis with deterministic AR 380-381 acceptance gate.

### Fixed
- **Section I (Abbreviations) bleed** (Unit 3) — primary cause of the 2026-04-25 100-doc backfill's 47% single-lc-word terms. AR 380-381: ~80 → 40 entries (50% reduction). PAM 350-58: 42 → 29 (-13). AR 405-90: 73 → 58 (-15). AR 40-3: 86 → 74 (-12). PAM 71-32: 62 → 59 (-3). AR 135-100: 151 → 149 (-2). 0 catastrophic regressions; 0 unexplained identity-fallbacks.
- v0.2.a inclusions (previously unreleased; bundled here): citation-fragment rejection, classifier tightening (multi-iter), invalid-term blocklist.

### Changed
- `SECTION_II_HEADER` and `SECTION_I_HEADER` regexes tightened with trailing constraint (Unit 3) — rejects body-text false positives like "Section II policies require..." while preserving production header forms ("Section II", "Section Il", "Section II — Terms").
- `tests/test_labels_classifier.py`: added `NEW_DOCS_SINCE_PREFIX_PDFS` allowlist for Unit 4's corpus expansion; expanded `REMOVED_SINCE_PREFIX` with 45 entries from Unit 3 narrowing.
- `tests/test_batch1_reconciled.py`: docstring updated to document that the 2 forbidden pairs survived v0.2.0 because they're orthogonal bug classes (inline-extraction noise + asterisk-prefix-split) Section II scoping didn't address. Assertion intentionally NOT inverted per Codex iter-1 #5 gating.

### Schema
- `definition-output-v1.json` extended with 4 new optional `Metadata` fields; schema_version unchanged at `"1"` (back-compat — existing v0.1.0 candidate-output still valid).

### Known limitations (deferred to follow-up units)
- Same-page boundary residue: when Section II header lives on a page with Section I continuation at top (e.g., AR 380-381 page 88), parser sees the whole page. ~6/40 entries (15%) on AR 380-381 are residue acronyms. Line-level boundary detection deferred.
- Asterisk-prefix term split: `*field` / `*engineer` style entries still split incorrectly (orthogonal to Section II scoping).
- Inline-extraction noise: TC 1-19.30 `dampen \nusually` extracted from body text page 102 — inline extraction runs over the entire document, not just the glossary range.
- Some legitimate Section II terms cut by Unit 3's end-boundary detection on a few docs (e.g., AR 405-90's "Tenant", "Surplus real estate"). Tracked as known regression in `REMOVED_SINCE_PREFIX`.

### Removed
- `tests/test_v0_2_a_corpus_refresh.py` and its fixtures (`v0_2_a_pre_fix_snapshot.json`, `v0_2_a_predecessor_defs.yaml`) — v0.2.a-specific regression test superseded by v0.2.0's `test_no_unexpected_classifier_flips`.

### Process
- All 6 units (Sub-Units 1a/1b/1c, Units 2-5) escalated at iter-1/2/3 of plan-review per the documented Option B pattern. Suggested CLAUDE.md rule for plan-review-rigor calibration on XS/S/M tasks documented in escalation docs (operator decides).

## [0.1.0] — Initial release

(Pre-v0.2.0 work; see git log for details.)
