# Unit 4 — hand-vet labels for Section-I-heavy docs

## Phase 0.a Classification

**fast-path-eligible** — additive validation-corpus expansion; no source-code changes; data files only. Single repo, fully reversible.

## 1. Problem statement

Per Unit 1's escalation and the meta-plan, the v0.1.0 extractor's Section I bleed bug was most visible on a small set of Army Regulations: AR 380-381, AR 637-2, AR 115-10, AR 700-13. Sub-Unit 1b captured 2 hand-confirmed forbidden pairs (TC + FM) from `labels-batch1.yaml`. **Unit 4 expands validation coverage** for the 4 Section-I-heavy worst-offender docs by:

1. Fetching their PDFs locally (gitignored — operator-side).
2. Sampling bad-output rows from the production `definitions` table (where the 100-doc backfill's bug output is preserved on Hetzner).
3. Appending ~100 auto-classified rows to `validation_set/labels-pending.tsv` documenting the bad-output patterns.
4. Adding `validation_set/labels-batch2-section-i.yaml` capturing the bug-pattern annotations (mirrors `labels-batch1.yaml` structure).

After Unit 5 (wheel republish + candidate-output regeneration with Unit-3 extractor), these "b" rows should NOT appear in regenerated candidate-output → that's the regression-detection signal.

## 2. Scope explicitly NOT in this unit

**No candidate-output regeneration.** Existing 27 candidate-output JSONs are pinned at v0.1.0 per Sub-Unit 1a's audit. Unit 5 (wheel republish) regenerates them.

**No `classifier_snapshot.yaml` update.** Per `tests/test_labels_classifier.py:test_no_unexpected_classifier_flips`, the snapshot test asserts `added == ∅` — adding new candidate-output JSONs to `validation_set/candidate-output/` would break the test. Unit 5 handles snapshot lifecycle (corpus refresh, fixture update).

**No PDFs committed to git.** PDFs in `validation_set/pdfs/` are gitignored per `validation_set/README.md`. Operator copies them locally; Unit 4 ensures they're available for distribution analysis but doesn't change the gitignore policy.

**No hand-vetting (`label` column population).** Per the existing `labels-pending.tsv` convention, the `label` column is empty across all 866 existing rows; the `auto_guess` column carries the classifier's verdict. Unit 4 follows this convention — populating `label` is a separate manual step (operator-side, future).

## 3. Verified context

- Production Hetzner `definitions` table has rows for all 4 Section-I-heavy docs: AR 380-381 (80 rows), AR 637-2 (46), AR 115-10 (155), AR 700-13 (29) = **310 total rows**. Verified via `psql` count query.
- AR 380-381 PDF is already in `validation_set/pdfs/` (added during Unit 3 distribution analysis).
- AR 637-2, AR 115-10, AR 700-13 PDFs NOT present locally; must fetch from `gs://fr-docs-prod/Regs - Army Pubs/Policy/`.
- `labels-pending.tsv` schema: `label\tauto_guess\tdoc\tpage\tterm\tdefinition_80` (verified in Sub-Unit 1a's audit).
- `labels-batch1.yaml` schema: `flips_to_bad: { doc_stem: [entry_index] }` + `extractor_bugs_logged: { bug_name: description }` (verified in Sub-Unit 1a's audit).

## 4. Approach

### 4.1 Fetch 3 missing PDFs

```bash
ssh hetzner 'gsutil cp "gs://fr-docs-prod/Regs - Army Pubs/Policy/AR 637-2 SEPARATION PAY_NONDISABILITY_AND LEVELS OF PAYMENT G-1 2022_08_18_OCR.pdf" /tmp/'
ssh hetzner 'gsutil cp "gs://fr-docs-prod/Regs - Army Pubs/Policy/AR 115-10 WEATHER SUPPORT FOR THE U.S. ARMY {AFI 15-157 (IP)} G-2 2010_11_15_OCR.pdf" /tmp/'
ssh hetzner 'gsutil cp "gs://fr-docs-prod/Regs - Army Pubs/Policy/AR 700-13 WORLDWIDE DEPARTMENT OF DEFENSE MILITARY MUNITIONS_AMMUNITION_LOGISTICS_SURVEILLANCE_EXPLOSIVES SAFETY REVIEW AND TECHNICAL ASSISTANCE PROGRAM G-4 2020_12_15_OCR.pdf" /tmp/'
scp hetzner:/tmp/AR_*.pdf /tmp/  # via local copy if direct path tricky
# Or use rsync; verify all 3 land in validation_set/pdfs/ locally
```

(Exact GCS paths confirmed by re-querying production `documents` table at execution time.)

### 4.2 Pull bad-output samples from prod

For each of the 4 docs, randomly sample 25 rows from production `definitions` table via:

```sql
SELECT d.canonical_id, def.term, left(def.definition, 80) AS definition_80, def.pdf_page_index
FROM definitions def JOIN documents d ON d.id = def.document_id
WHERE d.canonical_id = 'Army Regulation|AR XXX-YYY'
ORDER BY random() LIMIT 25;
```

Total: 4 × 25 = 100 rows. These are the BAD output the v0.1.0 extractor produced (preserved in prod from the 100-doc backfill). After Unit 5's wheel republish, these pairs should NOT appear in regenerated candidate-output (Section I bleed eliminated for the most part per Unit 3 distribution evidence).

### 4.3 Append rows to `labels-pending.tsv`

Format: `<empty_label>\tb\t<doc>\t<page>\t<term>\t<definition_80>` per existing convention. All 100 rows tagged `auto_guess='b'` since they're observed bad-output from the bug.

Doc-name normalization: strip "Army Regulation|" prefix from `canonical_id`. Result: `AR 380-381`, `AR 637-2`, `AR 115-10`, `AR 700-13`.

### 4.4 Create `labels-batch2-section-i.yaml`

Mirrors `labels-batch1.yaml`'s schema:

```yaml
# Batch 2 — Section-I-heavy docs (Unit 4 of v0.2.0).
# Captures bug-pattern annotations for the 4 worst-offender docs from the
# 2026-04-25 100-doc backfill. The bad-output rows are sampled into
# labels-pending.tsv with auto_guess='b'; this YAML records the
# bug-pattern taxonomy and per-doc summary.
#
# Source: prod definitions table on Hetzner (preserved post-backfill).

extractor_bugs_observed:
  - section_i_expansion_split: |
      Section I (Abbreviations) lines like "AAA / Army Audit Agency"
      were parsed as term='AAA' def='Army Audit Agency' on entry N
      and term='Army' def='Audit Agency' on entry N+1 (the parser split
      multi-word expansions at first whitespace). Unit 3 (Section II
      scoping) addresses this by excluding Section I from parsing range.
  - same_page_boundary_residue: |
      When Section II header lives on a page with Section I continuation
      at top of page (e.g., AR 380-381 page 88 has "TRADOC", "USACE",
      etc. acronyms then "Section Il/Terms" header then Section II
      content), the parser sees the whole page. Unit 3 reduces but does
      not eliminate this boundary residue. Documented limitation.

per_doc_summary:
  AR 380-381:
    v0_1_0_entry_count: 80
    section_structure_under_unit3: both
    expected_post_unit3_entry_count: ~40 (50% reduction; verified locally)
    notable_section_i_acronyms: [AAA, ACA, ACCM, AIS, AMC, USACE, USACIDC]
  AR 637-2:
    v0_1_0_entry_count: 46
    section_structure_under_unit3: TBD  # operator runs distribution analysis after Unit 4 PDF fetch
    notes: |
      Entry-count delta from v0.1.0 to Unit 3 will surface after PDF is
      fetched + measure_section_distribution.py runs locally.
  AR 115-10:
    v0_1_0_entry_count: 155
    section_structure_under_unit3: TBD
  AR 700-13:
    v0_1_0_entry_count: 29
    section_structure_under_unit3: TBD
```

Operator updates the `TBD` fields after running `scripts/measure_section_distribution.py` locally with the 3 new PDFs in place (not blocking for this PR).

## 5. Assumptions & alternatives

**Verified at planning time:**
- ✓ Prod `definitions` table has 310 rows across 4 docs (queried earlier).
- ✓ AR 380-381 PDF locally available; 3 others not.
- ✓ Schema for both labels-pending.tsv and labels-batch1.yaml documented in Sub-Unit 1a's audit.

**Load-bearing assumptions:**
- 25-rows-per-doc random sample is representative. Mitigation: distribution analysis on the full prod data shows the bug pattern is consistent within a doc (most rows from "both" docs are Section I expansion splits); a 25-row sample captures the dominant bug shape.
- Production `definitions` rows for these 4 docs were NOT modified after the 100-doc backfill halt. Verified: worker has been paused since the user said "stop the run"; no other writes happen.

**Alternative considered & rejected:**
- *Run extractor locally on the 4 PDFs and use that output as labels source.* Rejected: that would produce post-Unit-3 output (already-fixed). The point of Unit 4's labels is to capture pre-fix bad output as a regression detector for Unit 5.

## 6. The hard 30%

- **No code changes** — Unit 4 is data-files-only. The 137-test suite stays unaffected (verified by §7).
- **labels-pending.tsv format invariants** — header `label\tauto_guess\tdoc\tpage\tterm\tdefinition_80`; existing 866 rows have empty label. Unit 4's appended rows MUST match this format (empty label, `auto_guess='b'`, tab-separated, no embedded tabs in fields).
- **Definition_80 byte-exactness** — per Sub-Unit 1b's reconciliation, the prefix is `definition[:80]` on Unicode codepoints. SQL `left(definition, 80)` matches this when the 80-char prefix has no multi-byte UTF-8 boundary issues. Postgres `left()` is character-based, same convention. Verify by sampling 3 rows and comparing prefixes.
- **Doc-name normalization for join consistency** — labels-pending.tsv uses `AR XXX-YYY` (no "Army Regulation|" prefix). When sampling from prod, strip that prefix.
- **Sub-Unit 1b's corpus-pin test (#15) won't fail** because we're NOT touching candidate-output. Verified by §7.
- **Snapshot test (test_no_unexpected_classifier_flips) won't fail** because we're NOT touching candidate-output JSONs. Verified by §7.

## 7. Blast radius

**Files to modify:**
- `validation_set/labels-pending.tsv` (~100 new rows appended)

**Files to create:**
- `validation_set/labels-batch2-section-i.yaml` (~30 lines)

**Files to NOT modify:**
- `validation_set/candidate-output/*.json` (Unit 5's job)
- `validation_set/classifier_snapshot.yaml` (no candidate-output change)
- `tests/*` (no source-code change)
- `src/*` (no source-code change)

**Operator-side files (NOT in git):**
- `validation_set/pdfs/AR_637-2_*.pdf` etc. — gitignored, on disk only

**Existing tests:** 168 pass currently (Unit 3 + prior). Unit 4 is data-only; tests should continue passing. Verified by running `pytest tests/` after changes.

**Risk:** very low. Pure data addition; format-validated; operator can spot-check the 100 sampled rows.

## 8. Verification

1. **Pre-flight: existing tests pass.** `pytest tests/` → 168 pass.
2. **Format invariants:** every appended row has exactly 6 tab-separated fields; `label` field empty; `auto_guess` ∈ {g, b}; `page` numeric; `term` and `definition_80` non-empty.
3. **Definition byte-prefix correctness:** spot-check 3 random sampled rows by re-querying `definitions` table and comparing the 80-char prefix.
4. **Doc-name presence:** every appended row's `doc` field matches one of {AR 380-381, AR 637-2, AR 115-10, AR 700-13}; ~25 rows per doc.
5. **labels-batch2-section-i.yaml parses as YAML:** `python -c "import yaml; yaml.safe_load(open(...))"`.
6. **Existing tests still pass post-change:** `pytest tests/` → 168 pass.

## 9. Documentation impact

- `validation_set/labels-pending.tsv` extended (data file)
- `validation_set/labels-batch2-section-i.yaml` new (data file)
- `validation_set/README.md` no update needed (Sub-Unit 1c's "Honest artifact status" section accommodates new batch via the same data conventions; the artifact role doesn't change).
- CHANGELOG: deferred to Unit 5.

## 10. Completion criteria

1. 3 missing PDFs (AR 637-2, AR 115-10, AR 700-13) on local disk in `validation_set/pdfs/`.
2. ~100 new rows appended to `validation_set/labels-pending.tsv` (~25 per doc × 4 docs).
3. Every appended row format-valid (6 tab-separated fields, label empty, auto_guess ∈ {g,b}).
4. `validation_set/labels-batch2-section-i.yaml` exists and parses as YAML.
5. `pytest tests/` continues green (168 pass).
6. Plan doc + execution evidence committed.

## 11. Execution sequence

### Step 1: Verify pre-flight test state

```bash
.venv/bin/pytest tests/ 2>&1 | tail -3
```
**Verify:** 168 pass.

### Step 2: Fetch 3 missing PDFs

```bash
# Identify exact GCS paths
ssh hetzner 'PGPASSWORD=51dc49018d2e5e1bc51cd315ec4e94cc psql -h 172.18.0.1 -U fedresearch -d railway -tAc "SELECT canonical_id, gcs_key FROM documents WHERE canonical_id IN ('"'"'Army Regulation|AR 637-2'"'"', '"'"'Army Regulation|AR 115-10'"'"', '"'"'Army Regulation|AR 700-13'"'"');"'

# Fetch via gsutil on Hetzner, then scp to local
ssh hetzner 'mkdir -p /tmp/u4-pdfs && gsutil cp "gs://fr-docs-prod/<exact-key-for-AR-637-2>" /tmp/u4-pdfs/'
# Repeat for AR 115-10, AR 700-13
scp 'hetzner:/tmp/u4-pdfs/*.pdf' /Users/mw/code/fedresearch-dictionary-extractor/validation_set/pdfs/
```
**Verify:** `ls validation_set/pdfs/AR_637-2* AR_115-10* AR_700-13*` shows all 3.

### Step 3: Sample bad-output rows from prod

```bash
ssh hetzner 'PGPASSWORD=51dc49018d2e5e1bc51cd315ec4e94cc psql -h 172.18.0.1 -U fedresearch -d railway -tAc "
SELECT replace(d.canonical_id, '"'"'Army Regulation|'"'"', '"'"''"'"') AS doc,
       def.pdf_page_index AS page,
       def.term,
       left(def.definition, 80) AS definition_80
FROM definitions def JOIN documents d ON d.id = def.document_id
WHERE d.canonical_id IN (
  '"'"'Army Regulation|AR 380-381'"'"',
  '"'"'Army Regulation|AR 637-2'"'"',
  '"'"'Army Regulation|AR 115-10'"'"',
  '"'"'Army Regulation|AR 700-13'"'"'
)
ORDER BY d.canonical_id, def.pdf_page_index, def.term
" > /tmp/u4-rows.tsv'
scp hetzner:/tmp/u4-rows.tsv /tmp/u4-rows.tsv
wc -l /tmp/u4-rows.tsv
```

**Verify:** /tmp/u4-rows.tsv has ~310 lines (full count).

Then sample 25 rows per doc using awk/python; produce `labels-pending.tsv`-format lines (`<empty>\tb\t<doc>\t<page>\t<term>\t<definition_80>`).

```bash
.venv/bin/python -c "
import csv, random
random.seed(42)  # deterministic
rows_by_doc = {}
with open('/tmp/u4-rows.tsv', 'r', encoding='utf-8') as f:
    for line in f:
        parts = line.rstrip('\n').split('|', 3)  # psql output uses '|' as default separator
        if len(parts) != 4: continue
        doc, page, term, def80 = (p.strip() for p in parts)
        rows_by_doc.setdefault(doc, []).append((page, term, def80))

for doc, rows in rows_by_doc.items():
    sample = random.sample(rows, min(25, len(rows)))
    for page, term, def80 in sample:
        print(f'\tb\t{doc}\t{page}\t{term}\t{def80}')
" > /tmp/u4-append.tsv
wc -l /tmp/u4-append.tsv
head -3 /tmp/u4-append.tsv
```
**Verify:** ~100 lines (4 × 25); each has 6 tab-separated fields with empty first field.

### Step 4: Append to labels-pending.tsv

```bash
cat /tmp/u4-append.tsv >> validation_set/labels-pending.tsv
wc -l validation_set/labels-pending.tsv  # was 867 (header + 866 data); now ~967
```
**Verify:** new total line count = 867 + ~100. Existing rows untouched (head/tail comparison).

### Step 5: Format invariant check

```bash
LC_ALL=C awk -F'\t' '{print NF}' validation_set/labels-pending.tsv | sort -u
LC_ALL=C awk -F'\t' '$1!="" && NR>1 {print "WARN: nonempty label at line " NR}' validation_set/labels-pending.tsv | head
LC_ALL=C awk -F'\t' '$2!~/^[gb]$/ && NR>1 {print "WARN: invalid auto_guess at line " NR ": " $2}' validation_set/labels-pending.tsv | head
```
**Verify:** all rows have 6 fields; no nonempty `label` warnings; no invalid `auto_guess` warnings.

### Step 6: Create labels-batch2-section-i.yaml

Per §4.4 schema. Operator updates `TBD` fields after distribution analysis.

**Verify:**
```bash
.venv/bin/python -c "import yaml; d = yaml.safe_load(open('validation_set/labels-batch2-section-i.yaml')); print('keys:', list(d.keys())); print('per_doc:', list(d.get('per_doc_summary', {}).keys()))"
```
Expected: `keys: ['extractor_bugs_observed', 'per_doc_summary']`, 4 per-doc entries.

### Step 7: Existing-suite regression

```bash
.venv/bin/pytest tests/ 2>&1 | tail -3
```
**Verify:** 168 pass.

### Step 8: Commit + push + PR + merge

```bash
git add validation_set/labels-pending.tsv validation_set/labels-batch2-section-i.yaml docs/plans/2026-04-26-section-i-heavy-validation.md
git commit -m "feat(validation): Section-I-heavy worst-offender doc labels [Unit 4 of v0.2.0]"
git push -u origin feat/2026-04-26-section-i-heavy-validation
gh pr create --title "feat(validation): Section-I-heavy worst-offender doc labels [Unit 4]"
```

(PR + CI + merge handled by Phase 6 Sync & Close.)
