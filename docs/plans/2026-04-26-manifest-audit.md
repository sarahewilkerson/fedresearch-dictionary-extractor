# Sub-Unit 1a — validation_set manifest audit

## Phase 0.a Classification

**fast-path-eligible** — additive read-only audit script + markdown doc, single repo, fully reversible. Pass 1 indicators all clear; Pass 2 paths under `scripts/` and `validation_set/` outside exclusion patterns; Pass 3 self-checks all YES.

## 1. Problem statement

Unit 1's plan-review escalated three times because plan-time numbers about `validation_set/` didn't match repo reality (claimed 27 PDFs; actual 30 with 3 malformed names; PDFs gitignored; provenance drift between artifacts). Future units will plan against the same set. **Document the actual corpus state once, in a script-generated audit doc, so subsequent plans cite a single canonical source instead of re-deriving counts.**

This sub-unit produces:
- `scripts/audit_validation_manifest.py` — re-runnable script that inspects the corpus and writes a structured Markdown report directly to `validation_set/manifest_audit.md`.
- `validation_set/manifest_audit.md` — generated report committed alongside the script. Captures a snapshot at the commit's repo revision.

No tests, no oracle, no extractor changes. Pure data clarity for downstream planning.

## 2. Assumptions & alternatives

**Verified at planning time** (full source-of-truth audit per the rule the escalation surfaced):

- ✓ `validation_set/pdfs/` contains **30** entries; 27 with `.pdf` extension, 1 with `.p` (truncated extension: `AR_215-1_..._OCR.p`), 2 extensionless (`AR_190-9_...`, `ATP_5-0.3_...`).
- ✓ `validation_set/manifest.json` is the canonical local↔GCS mapping; for the malformed entries it records the truncated local paths, indicating the truncation is upstream (some platform/copy operation), not a script artifact.
- ✓ `validation_set/candidate-output/` contains **27 `.json` files + `NO_DEFINITIONS.txt`** = 28 entries.
- ✓ `validation_set/labels-pending.tsv` has 866 rows across 19 unique `doc` values; `label` column empty everywhere; `auto_guess` is `g` (698) or `b` (168).
- ✓ `validation_set/labels-batch1.yaml` has 5 `flips_to_bad` entries across 5 docs.
- ✓ Existing `validation_set/README.md` documents 30 PDFs with stratification (15 AR, 5 PAM, 4 FM, 3 ATP, 1 ADP, 1 TC, 1 TM).

**Load-bearing assumptions** (Codex iter-1 #2 + iter-2 #1, #2, #3: precise specification):

- **Stem-matching algorithm** (canonical join across all artifacts):
  ```
  pdf_stem(p) = basename, with trailing ".pdf" / ".p" stripped (truncated/extensionless cases keep the full filename as stem)
  json_stem(j) = basename without trailing ".json"
  normalize_pub_number(s) =
    1. If s starts with "DA PAM ", strip "DA " (→ "PAM 350-58")
    2. Replace spaces with "_"
    → returns a normalized prefix
  pdf_for_json(j) = unique pdf_stem starting with normalize_pub_number(j['source_pub_number'])
  ```

- **Cardinality rules** (Codex iter-2 #1):
  - PDF ↔ JSON: expected **1:1**. A JSON resolves to **exactly one** PDF stem. If multiple stems match the prefix, the JSON is reported as `ambiguous` (named in the Ambiguous Matches section); not silently joined.
  - PDF ↔ manifest entry: 1:1 by `local` path basename match.
  - PDF / JSON ↔ labels-pending docs: many rows can map to the same `doc`; expected 0-N rows per PDF.
  - PDF ↔ batch1 entries: 0-1 entry per PDF.
  - Acceptance: report shows exactly 0 ambiguous matches at the audit's snapshot commit. If non-zero, each is enumerated with rationale.

- **Duplicate / conflict detection** (Codex iter-2 #2):
  - Report explicitly lists duplicate `source_pub_number` values across JSONs (any 2+ JSONs with same value).
  - Report lists duplicate `local` paths in manifest.json.
  - Report lists duplicate `gcs_key` values in manifest.json.
  - Report lists conflicts where a manifest entry's `local` doesn't exist on disk OR a PDF on disk has no manifest entry.

- **Schema validation depth** (Codex iter-1 #6 + iter-2 #3):
  - manifest.json: top-level is `list`; every element is a `dict` with non-empty `str` values for `gcs_url`, `gcs_key`, `local`.
  - candidate-output JSONs: every file has top-level `dict` with non-empty `str` `source_pub_number` and `extractor_version`. (Exception: `NO_DEFINITIONS.txt` is excluded from JSON parsing.)
  - labels-pending.tsv: header row exactly `label\tauto_guess\tdoc\tpage\tterm\tdefinition_80`; every data row has 6 tab-separated fields.
  - labels-batch1.yaml: `flips_to_bad` key present and is a `dict[str, list[int]]`; `extractor_bugs_logged` key present.
  - Any failure → exit 2, message names the violated invariant. **NO partial reports** (Codex iter-2 #4: enforced by atomic write — see §4).

**Alternatives considered & rejected:**
- *Hand-write the audit doc once.* Rejected: not re-runnable.
- *Use `pyyaml.safe_load` strict mode without schema validation.* Rejected: silent partial parses on malformed input. Script does explicit shape checks.

## 3. Root cause analysis

N/A — audit task; no bug to diagnose. Justified per Phase 0.a + task-type criterion 4.

## 4. Approach

Single Python script that produces a **bidirectional reconciliation** (Codex iter-1 #1). For every artifact, identify whether each entry is matched, unmatched (orphaned), or ambiguous:

1. **Inventory phase** — list entries in each artifact:
   - `validation_set/pdfs/*` (any extension) — classify as `well-formed` (`.pdf`), `truncated-extension` (`.p`, `.pd`), or `extensionless`.
   - `validation_set/candidate-output/*.json` — read each, capture `source_pub_number` field.
   - `validation_set/manifest.json` — parse local↔GCS pairs.
   - `validation_set/labels-pending.tsv` — count rows per (`doc`, `auto_guess`); validate header.
   - `validation_set/labels-batch1.yaml` — list `flips_to_bad` entries; validate top-level keys.

2. **Schema validation** — explicit checks before any matching:
   - manifest.json: top-level is JSON array; each element has `gcs_url`, `gcs_key`, `local`.
   - labels-pending.tsv: header row is exactly `label\tauto_guess\tdoc\tpage\tterm\tdefinition_80`.
   - labels-batch1.yaml: top-level keys include `flips_to_bad` and `extractor_bugs_logged`.
   - Any failure → exit 2 with specific message.

3. **Reconciliation phase** — bidirectional matrix:
   - For each PDF entry: which JSON, which manifest entry, which labels-pending docs, which batch1 entry?
   - For each JSON: which PDF? (orphan if none.)
   - For each manifest entry: which PDF? (orphan if none.)
   - For each unique labels-pending `doc`: which PDF + JSON? (orphan if none.)
   - For each labels-batch1 doc: which PDF + JSON? (orphan if none.)

4. **Report phase** — write Markdown to `validation_set/manifest_audit.md` via **atomic write** (Codex iter-2 #4): generate full content in memory, write to `validation_set/manifest_audit.md.tmp`, then `os.replace()` to final path. On any prior-step failure, the existing committed report is unchanged.

   Required sections in fixed order:
   - **Header:** git revision only (`git rev-parse HEAD`); NO wall-clock date or time. Determinism (Codex iter-2 #7) requires byte-identical output across runs.
   - **Summary** counts.
   - **Schema validation** results (per artifact: PASS / specific FAIL).
   - **Malformed filenames** table.
   - **Bidirectional reconciliation** matrix (PDFs ↔ JSONs ↔ manifest ↔ labels).
   - **Orphan list** (per artifact: entries not matched anywhere).
   - **Ambiguous matches** (Codex iter-2 #1): JSONs whose `normalize_pub_number()` matched 0 or 2+ PDF stems. Expected: empty.
   - **Duplicate / conflict detection** (Codex iter-2 #2): duplicate source_pub_number, duplicate manifest local/gcs_key/gcs_url, missing-on-disk PDFs vs manifest, on-disk PDFs without manifest entries.
   - **DA-PAM normalized matches** table (3 entries expected).
   - **Pointer** to Sub-Units 1b and 1c.

**Script contract** (Codex iter-1 #4): script writes ONLY to `validation_set/manifest_audit.md` via atomic rename. Script's stdout is reserved for progress/error messages. No redirection-based workflow.

## 5. The hard 30%

- **Bidirectional reconciliation** (Codex iter-1 #1) is the load-bearing logic. PDF-centric matrix misses orphaned downstream artifacts; bidirectional catches them. Tests on known orphans verify.
- **Stem normalization** (Codex iter-1 #2) — explicit DA-PAM rule with audit trail in the report itself.
- **Schema validation** (Codex iter-1 #6) — fail loud, not silent partial reports. A "source-of-truth" doc that's silently wrong is worse than no doc.
- **Snapshot semantics** (Codex iter-1 #3) — the script is re-runnable and structural; the committed `.md` is a snapshot for the recording commit. Header records the git revision.
- **Determinism** — same input → byte-identical output. All listings sorted; no random sampling; no timestamps in body (only in header).
- **Targeted spot checks** (Codex iter-1 #5) — verification names specific edge cases: `.p` file → classified `truncated-extension`; `AR_190-9_...` (extensionless) → classified `extensionless`; `PAM 350-58` → matches `DA PAM 350-58` JSON via normalization; one labels-pending doc without candidate-output coverage → flagged as orphan.

## 6. Blast radius

**Files to create:**
- `scripts/audit_validation_manifest.py` (~150 lines)
- `validation_set/manifest_audit.md` (~100 lines, generated)

**Files to modify:** None.

**Existing tests:** unaffected.

**Downstream consumers:** Sub-Units 1b, 1c, and Unit 4 cite this audit doc as canonical corpus state.

**Realistic blast radius assessment** (Codex iter-1 #7):
- *Operational risk:* low (no runtime code paths affected; existing tests unchanged).
- *Planning risk:* medium. Wrong counts or wrong reconciliation in the audit doc propagate into Sub-Units 1b/1c/Unit 4 plans. Mitigated by §7's targeted spot checks against known edge cases — not just aggregate counts.

## 7. Verification strategy

**Machine-checkable verification** (Codex iter-2 #5): grep-based spot checks supplemented with exact-count assertions and a controlled negative test for the join logic itself.

1. **Determinism (header includes only git rev — Codex iter-2 #7):** run twice, byte-identical.
   ```bash
   .venv/bin/python scripts/audit_validation_manifest.py
   cp validation_set/manifest_audit.md /tmp/run1.md
   .venv/bin/python scripts/audit_validation_manifest.py
   diff /tmp/run1.md validation_set/manifest_audit.md
   ```
   Expected: empty diff.

2. **Exact-count assertions** (Codex iter-2 #5): the report's parseable summary block must match expected values.
   ```bash
   grep -E "^\- (PDFs|Well-formed PDFs|Malformed PDFs|JSONs|Manifest entries|labels-pending docs|batch1 flips|Ambiguous matches|Duplicate source_pub_number)" validation_set/manifest_audit.md
   ```
   Expected output (current corpus snapshot):
   ```
   - PDFs: 30
   - Well-formed PDFs: 27
   - Malformed PDFs: 3
   - JSONs: 27
   - Manifest entries: 30
   - labels-pending docs: 19
   - batch1 flips: 5
   - Ambiguous matches: 0
   - Duplicate source_pub_number: 0
   ```

3. **Malformed-filename classification:** exact 3 entries.
   ```bash
   awk '/^## Malformed filenames/,/^## /' validation_set/manifest_audit.md | grep -c "^| AR_215-1\|^| AR_190-9\|^| ATP_5-0.3"
   ```
   Expected: `3`.

4. **DA-PAM normalization:** exact 3 entries.
   ```bash
   awk '/^## DA-PAM normalized matches/,/^## /' validation_set/manifest_audit.md | grep -c "^| PAM "
   ```
   Expected: `3`.

5. **Negative test for join logic** (Codex iter-2 #5): introduce a duplicate `source_pub_number` and verify the audit reports it.
   ```bash
   # Pick one JSON, copy it under a new name with same source_pub_number
   cp validation_set/candidate-output/AR_135-100_*.json /tmp/dup.json.bak  # backup
   cp validation_set/candidate-output/AR_135-100_*.json validation_set/candidate-output/_DUPLICATE_TEST.json
   .venv/bin/python scripts/audit_validation_manifest.py
   grep -A 3 "Duplicate source_pub_number" validation_set/manifest_audit.md
   # Expect: report flags the duplicate
   rm validation_set/candidate-output/_DUPLICATE_TEST.json
   .venv/bin/python scripts/audit_validation_manifest.py  # restore clean state
   diff /tmp/run1.md validation_set/manifest_audit.md  # back to clean
   ```
   Expected: with duplicate, report shows non-empty Duplicate section. After cleanup, empty diff vs original.

6. **Schema-failure tests for ALL three artifacts** (Codex iter-2 #6): exit non-zero AND original report unchanged (atomic-write proof).
   ```bash
   ORIGINAL_HASH=$(shasum validation_set/manifest_audit.md | awk '{print $1}')
   # 6a: bad manifest.json
   cp validation_set/manifest.json /tmp/manifest.json.bak
   echo "{not valid json" > validation_set/manifest.json
   .venv/bin/python scripts/audit_validation_manifest.py; echo "exit-6a=$?"
   AFTER=$(shasum validation_set/manifest_audit.md | awk '{print $1}')
   [ "$ORIGINAL_HASH" = "$AFTER" ] && echo "atomic-write OK 6a" || echo "FAIL 6a: report corrupted"
   mv /tmp/manifest.json.bak validation_set/manifest.json
   # 6b: bad TSV header
   cp validation_set/labels-pending.tsv /tmp/tsv.bak
   echo "wrong\theader" > validation_set/labels-pending.tsv
   .venv/bin/python scripts/audit_validation_manifest.py; echo "exit-6b=$?"
   AFTER=$(shasum validation_set/manifest_audit.md | awk '{print $1}')
   [ "$ORIGINAL_HASH" = "$AFTER" ] && echo "atomic-write OK 6b" || echo "FAIL 6b"
   mv /tmp/tsv.bak validation_set/labels-pending.tsv
   # 6c: missing batch1 key
   cp validation_set/labels-batch1.yaml /tmp/batch1.bak
   echo "wrong_top_key: 1" > validation_set/labels-batch1.yaml
   .venv/bin/python scripts/audit_validation_manifest.py; echo "exit-6c=$?"
   AFTER=$(shasum validation_set/manifest_audit.md | awk '{print $1}')
   [ "$ORIGINAL_HASH" = "$AFTER" ] && echo "atomic-write OK 6c" || echo "FAIL 6c"
   mv /tmp/batch1.bak validation_set/labels-batch1.yaml
   ```
   Expected: each `exit-6x=2`; each "atomic-write OK 6x"; final state restored to clean.

7. **Existing test suite regression:**
   ```bash
   .venv/bin/pytest tests/ 2>&1 | tail -5
   ```
   Expected: green.

## 8. Documentation impact

- **`validation_set/manifest_audit.md`** — new (the deliverable).
- **`README.md`** — no update in this sub-unit; Sub-Unit 1c handles the README rewrite.
- **CHANGELOG** — deferred to Unit 5.

## 9. Completion criteria (technical acceptance — Codex iter-1 #8)

Technical acceptance is independent of PR/CI/merge mechanics; those happen in Phase 6 (`/review-execution` Sync & Close).

1. **Structural** (script behavior, robust to corpus change):
   1. `scripts/audit_validation_manifest.py` exists.
   2. Running `python scripts/audit_validation_manifest.py` exits 0 and writes (or overwrites) `validation_set/manifest_audit.md`.
   3. Running the script twice produces byte-identical output (determinism).
   4. With deliberately broken `manifest.json` / malformed TSV header / missing batch1 key, the script exits non-zero with a specific error message naming the violated invariant.
   5. Report contains the seven required sections: header (with git rev), summary, schema-validation, malformed-filename table, reconciliation matrix, orphan list, DA-PAM normalization table, "next steps" pointer.

2. **Snapshot** (specific to current commit, may evolve):
   1. Generated report's malformed-filename table has 3 entries: `AR_215-1_..._OCR.p`, `AR_190-9_...`, `ATP_5-0.3_...`.
   2. DA-PAM normalization table has 3 entries (PAM 190-45, PAM 350-58, PAM 71-32).
   3. Summary counts: 30 PDFs (27 well-formed, 3 malformed); 27 JSONs; 19 labels-pending docs; 5 batch1 flips.

3. **Regression:** `pytest tests/` continues green.

(Delivery — PR opening, CI green, merge — handled by Phase 6's `/review-execution` Sync & Close protocol; not part of technical acceptance.)

## 10. Execution sequence

### Step 1: Implement audit script

Write `scripts/audit_validation_manifest.py` per §4. Bidirectional reconciliation; schema validation; writes directly to `validation_set/manifest_audit.md`.

**Verify:**
```bash
.venv/bin/python scripts/audit_validation_manifest.py; echo "exit=$?"
ls -la validation_set/manifest_audit.md
head -20 validation_set/manifest_audit.md
```
Expected: exit 0; file exists; header shows git rev + summary counts.

### Step 2: Determinism check

```bash
cp validation_set/manifest_audit.md /tmp/run1.md
.venv/bin/python scripts/audit_validation_manifest.py
diff /tmp/run1.md validation_set/manifest_audit.md
```
**Verify:** empty diff.

### Step 3: Targeted spot checks

Per §7 items 2-4. Each grep command runs and shows the expected pattern.

```bash
grep -A 5 "Malformed filenames" validation_set/manifest_audit.md
grep -A 5 "DA PAM" validation_set/manifest_audit.md
grep -A 5 "Orphan" validation_set/manifest_audit.md
```
**Verify:** all three sections populated with the expected entries.

### Step 4: Schema-validation behavior check

```bash
cp validation_set/manifest.json /tmp/manifest.json.bak
echo "{not valid json" > validation_set/manifest.json
.venv/bin/python scripts/audit_validation_manifest.py; echo "exit=$?"
mv /tmp/manifest.json.bak validation_set/manifest.json
```
**Verify:** exit 2 with message naming `manifest.json`.

Restore manifest and re-run script:
```bash
.venv/bin/python scripts/audit_validation_manifest.py
diff /tmp/run1.md validation_set/manifest_audit.md
```
**Verify:** empty diff (returned to clean state).

### Step 5: Existing-suite regression

```bash
.venv/bin/pytest tests/ 2>&1 | tail -5
```
**Verify:** green.

### Step 6: Commit

```bash
git add scripts/audit_validation_manifest.py validation_set/manifest_audit.md
git commit -m "feat(audit): validation_set manifest audit script + report [plan: 2026-04-26-manifest-audit]"
```
**Verify:** `git log --oneline -1` shows the commit.

(PR open, CI run, merge handled by Phase 6's Sync & Close — not in this section.)
