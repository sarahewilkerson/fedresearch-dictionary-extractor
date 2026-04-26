# validation_set Manifest Audit

**Repo revision:** `38b0d48` (parent of this commit; data captured 2026-04-26)
**Method:** hand-audit per Sub-Unit 1a (escalation Option B). The script-based approach was abandoned after `/review-plan` produced 8/7/8 findings across 3 iterations on what was scoped as a 30-min XS task — see `docs/plans/2026-04-26-manifest-audit-ESCALATION.md`.
**Purpose:** canonical corpus state for Sub-Units 1b, 1c, and Unit 4 to cite. Regenerate by hand if the corpus changes meaningfully.

---

## Summary

| Artifact | Count | Notes |
|---|---|---|
| `validation_set/pdfs/*` | 30 | 27 well-formed `.pdf` + 3 malformed |
| `validation_set/candidate-output/*.json` | 27 | + 1 sentinel (`NO_DEFINITIONS.txt`) |
| `validation_set/manifest.json` entries | 27 | 3 PDFs on-disk are NOT in manifest (see §Manifest gaps) |
| `validation_set/labels-pending.tsv` rows | 866 | 698 `g` + 168 `b` in `auto_guess`; **`label` column EMPTY in all rows** |
| `validation_set/labels-pending.tsv` unique docs | 19 | subset of corpus |
| `validation_set/labels-batch1.yaml` flips_to_bad | 5 | 5 distinct docs |

---

## Malformed filenames (3)

| File | Classification | In manifest? | In candidate-output? |
|---|---|---|---|
| `AR_215-1_MILITARY_MORALE_..._OCR.p` | truncated-extension (`.p` instead of `.pdf`) | yes | no (orphan PDF) |
| `AR_190-9_ABSENTEE_DESERTER_..._AGENCIES` | extensionless | yes | no (orphan PDF) |
| `ATP_5-0.3_MULTI-SERVICE_..._AFTTP_3-2.87` | extensionless | yes | no (orphan PDF) |

The truncation appears upstream of this repo (`manifest.json` records the same truncated paths). Not fixed in this sub-unit; flagged for a separate decision (Unit 4 may want to rename/re-fetch).

---

## Manifest gaps (PDFs on disk but missing from manifest.json)

3 short-name PDFs exist on disk and have matching JSONs in candidate-output, but lack `manifest.json` entries. The manifest only covers the 27 long-descriptive-name PDFs.

| PDF on disk | Matching candidate-output JSON | In manifest? |
|---|---|---|
| `AR_600-20.pdf` | `AR_600-20.json` | no |
| `PAM_600-3.pdf` | `PAM_600-3.json` | no |
| `TC_1-19.30.pdf` | (no — only `TC_1-19.30_THE_ARMY_BAND_..._OCR.json` long-name version) | no |

Likely an artifact of how the validation set was assembled (short names vs descriptive names for the same docs). Not fixed in this sub-unit.

---

## Reconciliation matrix

### PDFs ↔ candidate-output JSONs (1:1 by filename stem)

- **27 well-formed PDFs all have matching JSONs.** No orphan JSONs.
- **3 malformed PDFs have NO matching JSON** (orphan PDFs — listed in §Malformed filenames).
- 0 ambiguous matches (no JSON's `source_pub_number` resolves to multiple PDF stems).

### PDFs ↔ manifest.json

- 27 of 30 PDFs have manifest entries.
- 3 missing per §Manifest gaps.
- 0 manifest entries pointing at non-existent files.

### labels-pending.tsv → JSONs (lookup via `doc` field)

- **All 19 unique TSV docs match a JSON's `source_pub_number`** (with `DA PAM` ↔ `PAM` normalization for 3 of them).
- 0 TSV docs without coverage.

### labels-batch1.yaml → JSONs

- All 5 batch1 doc keys resolve to candidate-output JSONs.
- **Flip indices are stale** vs current candidate-output: TC_1-19.30 idx 1 looks 0-based (entries[1] = `dampen \nusually`, the bad one); FM_3-34 idx 4 looks 1-based (entries[3] = `*field`). Provenance drift since 2026-04-22 capture.
- **Sub-Unit 1b's job:** reconcile these 5 indices to current candidate-output by content.

---

## DA PAM ↔ PAM normalization

JSON `source_pub_number` field uses `DA PAM`; labels-pending.tsv uses `PAM`. 6 JSONs have this prefix; 3 of them are referenced from the TSV.

| JSON `source_pub_number` | Normalized form | Referenced in labels-pending.tsv? |
|---|---|---|
| `DA PAM 190-45` | `PAM 190-45` | yes (29 rows) |
| `DA PAM 350-58` | `PAM 350-58` | yes (36 rows) |
| `DA PAM 71-32` | `PAM 71-32` | yes (99 rows) |
| `DA PAM 385-64` | `PAM 385-64` | no |
| `DA PAM 600-3` | `PAM 600-3` | no |
| `DA PAM 770-3` | `PAM 770-3` | no |

Sub-Units 1b/1c/Unit 4: when joining TSV docs to JSONs, normalize the JSON side via `s.replace('DA PAM ', 'PAM ')`.

---

## labels-pending.tsv breakdown

19 unique docs, 866 rows total (698 g, 168 b). Per-doc counts (from the audit data):

| Doc | g | b | Total |
|---|---|---|---|
| AR 135-100 | 167 | 94 | 261 |
| AR 600-20 | 104 | 9 | 113 |
| PAM 71-32 | 92 | 7 | 99 |
| AR 40-5 | 100 | 16 | 116 |
| AR 40-3 | 72 | 11 | 83 |
| AR 405-90 | 60 | 7 | 67 |
| AR 12-15 | 2 | 1 | 3 |
| AR 190-55 | 5 | 1 | 6 |
| AR 672-20 | 8 | 4 | 12 |
| ADP 3-07 | 8 | 0 | 8 |
| ATP 1-05.01 | 0 | 1 | 1 |
| ATP 4-35 | 2 | 1 | 3 |
| FM 3-34 | 2 | 3 | 5 |
| FM 3-55 | 2 | 1 | 3 |
| FM 4-1 | 1 | 0 | 1 |
| FM 6-02 | 14 | 1 | 15 |
| PAM 190-45 | 25 | 4 | 29 |
| PAM 350-58 | 31 | 5 | 36 |
| TC 1-19.30 | 3 | 2 | 5 |

**Important caveat:** the `label` column is empty for ALL 866 rows. The `auto_guess` column carries the g/b classification. This means **labels-pending.tsv is the auto-classifier's output awaiting human review, NOT a hand-vetted oracle.** Sub-Unit 1c's README rewrite will document this prominently.

---

## labels-batch1.yaml flips_to_bad

5 entries from a 2026-04-22 hand spot-check:

| Doc | Index | Indexing convention (inferred) | Current candidate-output entry at that index | Bug pattern (per `extractor_bugs_logged`) |
|---|---|---|---|---|
| TC_1-19.30 | 1 | 0-based | `dampen \nusually` (entries[1]) | column-bleed / page_footer_in_entries |
| AR_190-55 | 5 | 0-based or 1-based (ambiguous; both look plausible) | `RCM` (entries[4]) or `SECARMY` (entries[5]) | uncertain — needs Sub-Unit 1b reconciliation |
| ADP_3-07 | 8 | out of bounds (< 8 entries in current JSON) | — | document is small; index drifted |
| AR_12-15 | 2 | 0-based or 1-based (ambiguous) | `USMC` or `USN` | uncertain — needs Sub-Unit 1b reconciliation |
| FM_3-34 | 4 | 1-based | `*field` (entries[3]) | asterisk_term_split |

**Sub-Unit 1b's job:** match each entry by CONTENT (using the named bug patterns: `asterisk_term_split`, `section_header_as_term`, `page_footer_in_entries`) and capture concrete `(doc, term, def[:80])` triples in `validation_set/batch1_reconciled.yaml`.

---

## Findings for downstream sub-units

**Sub-Unit 1b (batch1 reconciliation + strict regression test):**
- 5 batch1 flips need content-based reconciliation against current candidate-output (not stale indices).
- TC_1-19.30 idx 1 → `dampen \nusually` is unambiguous and matches `page_footer_in_entries` pattern (def starts with `usually` after a newline).
- FM_3-34 idx 4 → `*field` matches `asterisk_term_split` pattern.
- The remaining 3 (AR_190-55, ADP_3-07, AR_12-15) require manual inspection of the source PDFs.
- Strict regression test should use pinned candidate-output JSONs (no PDF re-extraction needed, runs in default CI).

**Sub-Unit 1c (honest artifact documentation):**
- README must clarify that `label` column in labels-pending.tsv is empty (not hand-vetted).
- Document the 3 malformed PDFs and 3 manifest gaps as known issues.
- Document the `DA PAM ↔ PAM` normalization rule.

**Unit 4 (hand-vetting Section-I-heavy docs for v0.2.0):**
- Use this audit doc + Sub-Unit 1c's README for the canonical corpus state.
- The 4 worst-offender Section-I-heavy docs from the 100-doc backfill (AR 380-381, AR 637-2, AR 115-10, AR 700-13) are NOT currently in `validation_set/pdfs/` — Unit 4 adds them.

---

## What this audit does NOT do

- Does NOT fix malformed PDF filenames (escalates to a separate decision).
- Does NOT add manifest entries for the 3 short-name PDFs (out of scope).
- Does NOT regenerate this report automatically (script-based approach abandoned per escalation).
- Does NOT validate the schemas of any artifact at runtime (this is a one-time snapshot).
