# Unit 1 — v0.1.0 snapshot oracle + auto-classifier baseline

## Phase 0.a Classification

**fast-path-eligible** — additive test infrastructure (3-4 new files, 0 modified source files), single repo, fully reversible. Pass 1 indicators all clear; Pass 2 likely-touched files (`tests/`, `scripts/`, `validation_set/`) all outside exclusion patterns; Pass 3 self-checks all YES (one-sentence outcome, single git revert restores prior state, no data-at-rest / credentials / authn touched).

## 1. Problem statement

The v0.2.0 decomposition (`docs/plans/2026-04-26-v0.2-decomposition.md`) needs an oracle infrastructure that subsequent units (2-5) can use to demonstrate quality improvements (or no regression) when extractor logic changes. Two artifacts already exist in `validation_set/`:

- **`labels-batch1.yaml`** — 5 hand-flip indices for 5 small docs, captured 2026-04-22. **Indices are stale** vs current candidate-output (verified at planning: TC_1-19.30 idx 1 looks 0-based, FM_3-34 idx 4 looks 1-based — content drift since capture).
- **`labels-pending.tsv`** — 866 rows across 19 docs. Verified at planning: `label` column is **empty for ALL rows**; the g/b values live in `auto_guess`. So this is **auto-classifier output awaiting human review**, NOT a hand-vetted oracle. Header confirms: `label\tauto_guess\tdoc\tpage\tterm\tdefinition_80`. Corpus audit at planning: 468/698 g rows and 9/168 b rows match current candidate-output by byte-exact prefix — provenance drift.

The honest story: hand-vetting fresh labels is Unit 4's scope. Unit 1 builds regression infrastructure from what we DO have, framed honestly.

## 2. Approach

Build TWO artifacts.

### 2.1 Snapshot-equality oracle (strict, machine-enforced, default CI)

Capture current `validation_set/candidate-output/*.json` as a committed snapshot. The test re-runs the extractor against the corresponding PDFs and asserts byte-for-byte JSON equality (modulo a frozen exclusion list of non-deterministic fields).

- **Use:** When Unit 2/3 changes the extractor, this test fails. Operator inspects the diff (intentional change vs accidental drift), then re-baselines via `scripts/regenerate_snapshot.py`.
- **Strength:** Catches ANY change in extractor output.
- **Limitation:** Doesn't measure quality — quality is the auto-baseline (§2.2) plus manual review.

### 2.2 Auto-classifier baseline measurement (informational, with invalid-baseline branch)

Run the `auto_guess` column from `labels-pending.tsv` against current extractor output. Compute `good_emit_rate`, `bad_emit_rate`, `not_in_output_rate` per doc. Write machine-readable JSON + human-readable Markdown.

**Invalid-baseline branch (Codex iter-2 #4):** if `g_match_rate < 50%` OR `total_unmatched_pairs > 100`, the script:
1. Writes the metrics file with an explicit `"baseline_status": "UNUSABLE"` field at the top level
2. Writes a sibling marker file `validation_set/auto_baseline_v0.1.0.UNUSABLE.txt` explaining the drift
3. Prints a loud warning to stderr
4. Exits 0 (no false success on the script itself, but the artifact is clearly marked unusable)

In the unusable case, Unit 4 (hand-vetting) becomes a hard prerequisite for Units 2-5's quality measurements; the snapshot oracle (§2.1) remains the strict regression detector.

### 2.3 Defer hand-vetting

Hand-vetting fresh ground truth (resolving batch1.yaml's index drift, hand-confirming Section-I-heavy docs) is **out of scope for Unit 1**. Unit 4 owns it. Keeping Unit 1 narrow lets us land regression infrastructure quickly.

## 3. Authoritative manifest (Codex iter-2 #1)

**Source of truth:** `validation_set/pdfs/*.pdf`. The set of PDFs IS the manifest. All other coverage maps to it.

```
N_PDFS = count(validation_set/pdfs/*.pdf)
N_SNAPSHOTS = count(validation_set/v0.1.0_snapshot/*.json)
N_CANDIDATE_OUTPUT = count(validation_set/candidate-output/*.json)
```

Invariants enforced by tests in default CI:

- `N_SNAPSHOTS == N_PDFS` (every PDF has exactly one snapshot)
- For every `pdf in validation_set/pdfs/`, there exists exactly one `snapshot.json` with the same stem
- For every `snapshot in validation_set/v0.1.0_snapshot/`, there exists exactly one PDF with the same stem
- `N_CANDIDATE_OUTPUT == N_PDFS` (existing pre-condition; if this fails, abort Unit 1 before any work)

Any drift is a hard test failure with a specific message naming the missing/extra file. **No `pytest.skip` on missing PDF — it's a fail.**

Planning-time audit:

```
$ ls validation_set/pdfs/*.pdf | wc -l
27
$ ls validation_set/candidate-output/*.json | wc -l
27 (excluding NO_DEFINITIONS.txt + AR_600-20.json + PAM_600-3.json)
```

Wait — actual count from earlier survey shows 28 entries in candidate-output (one is `NO_DEFINITIONS.txt`). The manifest test must validate 1:1 mapping by **stem**, ignoring non-`.json` files. Step 1 verifies this.

## 4. Assumptions & alternatives

**Verified at planning time:**
- ✓ `label` column empty across all 866 rows; `auto_guess` carries the classification (`168 b, 698 g`).
- ✓ Corpus-wide byte-exact prefix match: 468/698 g rows and 9/168 b rows match current candidate-output. Provenance drift confirmed.
- ✓ Candidate-output files are tagged `extractor_version: "0.1.0"`.
- ✓ batch1.yaml's flip indices don't reliably map to current candidate-output.

**Load-bearing assumptions for §2.1 (snapshot):**
- Extractor produces deterministic output across runs of v0.1.0, modulo a frozen-by-execution-Step-1 set of non-deterministic fields. **Step 1 audits ALL 27 PDFs, not 1** (Codex iter-2 #2). If any PDF shows variation beyond the documented exclusion set, that PDF is investigated and its variation either fixed or added to the frozen exclusion list with explicit justification in the snapshot regeneration script.
- Re-running extraction across all 27 PDFs in CI completes in budget. Planning estimate: 27 × ~5s avg = ~135s. Pyproject's existing `lint-and-test` job already runs the test suite; adding 135s is acceptable. **No fallback to file-vs-file comparison** (Codex iter-2 #3); if runtime is excessive, the alternative is a parallel-parameterized strategy or a separate CI job, but never substituting away the actual extraction.

**Load-bearing assumptions for §2.2 (baseline):**
- Byte-exact prefix match using **Python `str.__getitem__([:80])` on Unicode code points**. Codified via a slicing-contract test (Codex iter-2 #5) that asserts the convention on **5+ exemplar rows** drawn from labels-pending.tsv, not 1.
- The 50% / 100-pair threshold for "unusable baseline" is documented in §2.2 and operationalized by the script (writes the UNUSABLE marker if either condition trips).

## 5. Root cause analysis

N/A — additive infrastructure task; no bug to diagnose. Justified per Phase 0.a + task-type criterion 4.

## 6. The hard 30%

- **Determinism audit must be full-corpus** (Codex iter-2 #2). Step 1 runs every PDF twice and diffs. Any variation beyond `extraction_timestamp` halts execution; remediation decision is required (either fix the source, or freeze a longer exclusion list with per-field justification — never silent expansion).
- **Manifest invariants are tested, not just documented** (Codex iter-2 #1). A `test_manifest_consistency` test asserts the four invariants in §3 in default CI.
- **No fallback for runtime** (Codex iter-2 #3). The strict oracle path is the strict oracle path. If runtime exceeds budget, the plan switches to a parametric / parallelized strategy, NOT to file equality.
- **Invalid-baseline branch is operationalized** (Codex iter-2 #4). The auto-baseline script EMITS the UNUSABLE marker programmatically; subsequent units that depend on the baseline check for the marker before consuming the metrics.
- **Slicing contract test asserts on 5+ rows** (Codex iter-2 #5), drawn from across docs. If any row mismatches, the script halts and surfaces the encoding diagnostic.
- **Snapshot regeneration discipline.** When Units 2/3 land and snapshot updates, `scripts/regenerate_snapshot.py` prints a structured diff. Operator must commit the diff explicitly; CI does NOT auto-update.

## 7. Blast radius

**Files to create:**
- `tests/test_v0_1_0_snapshot.py` (~100 lines) — runs in default CI; parametric over manifest
- `tests/test_manifest_consistency.py` (~30 lines) — runs in default CI; asserts §3 invariants
- `validation_set/v0.1.0_snapshot/` directory with one JSON per PDF
- `scripts/regenerate_snapshot.py` (~80 lines)
- `scripts/measure_auto_baseline.py` (~140 lines, includes slicing self-test on 5+ rows + invalid-baseline branch)
- `validation_set/auto_baseline_v0.1.0.json` (machine-readable; includes `baseline_status` field) OR `validation_set/auto_baseline_v0.1.0.UNUSABLE.txt` (if drift exceeds threshold)
- `validation_set/auto_baseline_v0.1.0.md` (~50 lines, generated companion)

**Files to modify:** `README.md` (add Validation Oracles section).

**Existing tests:** must continue to pass.

**Downstream consumers:** Unit 2/3 must re-baseline snapshots when extraction logic changes. Unit 4 hand-vets new labels (independent of §2.2 baseline status — replaces it). Unit 5 final-check.

**Risk of breaking:**
- Step 1 might discover non-determinism beyond `extraction_timestamp`. Plan covers this: remediation decision required, no silent expansion.
- CI runtime might exceed budget. Plan covers this: switch to parametric/parallelized, not file-vs-file fallback.

## 8. Verification strategy

Each step has concrete `Verify:` line in §10. Summary:

- **§2.1 snapshot:** determinism audit (Step 1), inverse check (Step 4), default-CI green (Step 7).
- **§2.2 baseline:** slicing self-test on 5+ rows (Step 5), invalid-baseline branch behavior (Step 5), idempotency check (Step 5).
- **Manifest invariants:** `test_manifest_consistency.py` runs in default CI (Step 6, included in Step 7's pytest run).
- **Coverage completeness:** Step 6 confirms `pytest --collect-only -k snapshot` reports exactly N_PDFS tests collected.

## 9. Documentation impact

- **New deliverables (counts as docs):** `validation_set/v0.1.0_snapshot/`, baseline JSON+MD (or UNUSABLE marker).
- **README.md** — Validation Oracles section.
- **CHANGELOG** — deferred to Unit 5.

## 10. Completion criteria (operationalized — Codex iter-2 #5)

Every criterion is a checkable command, not prose.

1. `validation_set/v0.1.0_snapshot/` exists with N JSON files where N == N_PDFS. Verified by `test_manifest_consistency.py`.
2. `pytest tests/` passes (default invocation, no marker). Includes `test_v0_1_0_snapshot.py` and `test_manifest_consistency.py`.
3. `pytest tests/test_v0_1_0_snapshot.py --collect-only -q | grep -c "test_snapshot_equality"` returns N_PDFS — proves full-manifest coverage in CI.
4. Step 1 determinism audit log committed at `validation_set/v0.1.0_snapshot/_determinism_audit.md`, listing every PDF and observed non-deterministic fields. Frozen exclusion list documented at top of `scripts/regenerate_snapshot.py`.
5. `scripts/measure_auto_baseline.py` either:
   - (success path) writes `validation_set/auto_baseline_v0.1.0.json` with `"baseline_status": "USABLE"` AND `validation_set/auto_baseline_v0.1.0.md`. Match rates documented; threshold not breached.
   - OR (drift path) writes `validation_set/auto_baseline_v0.1.0.json` with `"baseline_status": "UNUSABLE"` AND `validation_set/auto_baseline_v0.1.0.UNUSABLE.txt` explaining the drift. Subsequent units check this file before consuming.
6. Slicing self-test: `scripts/measure_auto_baseline.py --self-test` exits 0 after asserting the slicing contract on 5+ exemplar rows; non-zero on any mismatch.
7. README updated with Validation Oracles section. `grep -A 5 "Validation oracles" README.md` shows it.
8. PR opened, CI green (`lint-and-test (3.11)`, `lint-and-test (3.12)`, `build-wheel`), squash-merged. Merge SHA captured for Unit 5.

## 11. Execution sequence

### Step 1: Full-corpus determinism audit (Codex iter-2 #2)

Audit all 27 PDFs for non-deterministic output. Write report.

```bash
cd /Users/mw/code/fedresearch-dictionary-extractor
mkdir -p validation_set/v0.1.0_snapshot
.venv/bin/python -c "
import json, glob, hashlib
from pathlib import Path
from fedresearch_dictionary_extractor.core.analyzer import analyze_pdf

pdfs = sorted(Path('validation_set/pdfs').glob('*.pdf'))
print(f'# Determinism audit: {len(pdfs)} PDFs')
print()
print('| PDF | Run 1 hash | Run 2 hash | Identical (modulo timestamp)? | Variant fields |')
print('|---|---|---|---|---|')
all_variant_fields = set()
for pdf in pdfs:
    o1 = analyze_pdf(str(pdf), profile='army')
    o2 = analyze_pdf(str(pdf), profile='army')
    o1.pop('extraction_timestamp', None)
    o2.pop('extraction_timestamp', None)
    s1 = json.dumps(o1, sort_keys=True)
    s2 = json.dumps(o2, sort_keys=True)
    h1 = hashlib.sha256(s1.encode()).hexdigest()[:8]
    h2 = hashlib.sha256(s2.encode()).hexdigest()[:8]
    variants = []
    if o1 != o2:
        for k in set(o1.keys()) | set(o2.keys()):
            if o1.get(k) != o2.get(k):
                variants.append(k)
        all_variant_fields.update(variants)
    print(f'| {pdf.name[:40]:40s} | {h1} | {h2} | {o1 == o2} | {variants if variants else \"-\"} |')
print()
print(f'## All variant fields across corpus: {sorted(all_variant_fields)}')
" > validation_set/v0.1.0_snapshot/_determinism_audit.md
cat validation_set/v0.1.0_snapshot/_determinism_audit.md | tail -30
```

**Verify:** every row reports `True` for "Identical (modulo timestamp)". If ANY row reports `False`, halt — diagnose the variant field, decide remediation (fix the source OR add to frozen exclusion list with justification), then re-run audit. Do NOT proceed to Step 2 until the audit shows full determinism.

Commit:
```bash
git add validation_set/v0.1.0_snapshot/_determinism_audit.md
git commit -m "audit(determinism): full-corpus 27-PDF determinism check

All PDFs produce identical output across runs modulo extraction_timestamp."
```

### Step 2: Generate snapshot files

Write `scripts/regenerate_snapshot.py`. Frozen exclusion list at top of file:

```python
# FROZEN exclusion list — derived from Step 1 audit (commit <SHA>).
# These fields vary across runs of v0.1.0 and must be stripped before snapshot equality.
# DO NOT expand without re-running the determinism audit and updating this comment.
NONDETERMINISTIC_FIELDS = frozenset(['extraction_timestamp'])
```

Generate snapshots:
```bash
.venv/bin/python scripts/regenerate_snapshot.py --create-initial
ls validation_set/v0.1.0_snapshot/*.json | wc -l
ls validation_set/pdfs/*.pdf | wc -l
```

**Verify:** snapshot count == PDF count (manifest 1:1).

Commit:
```bash
git add scripts/regenerate_snapshot.py validation_set/v0.1.0_snapshot/*.json
git commit -m "feat(snapshot): v0.1.0 oracle snapshots from determinism-audited candidate-output

Frozen exclusion list: extraction_timestamp only.
N_SNAPSHOTS == N_PDFS == 27."
```

### Step 3: Manifest invariant test

Write `tests/test_manifest_consistency.py`:

```python
from pathlib import Path

PDF_DIR = Path(__file__).parent.parent / 'validation_set' / 'pdfs'
SNAPSHOT_DIR = Path(__file__).parent.parent / 'validation_set' / 'v0.1.0_snapshot'

def test_pdfs_and_snapshots_one_to_one():
    pdf_stems = {p.stem for p in PDF_DIR.glob('*.pdf')}
    snap_stems = {s.stem for s in SNAPSHOT_DIR.glob('*.json')}
    missing_snaps = pdf_stems - snap_stems
    extra_snaps = snap_stems - pdf_stems
    assert not missing_snaps, f"PDFs missing snapshots: {missing_snaps}"
    assert not extra_snaps, f"Snapshots without PDFs: {extra_snaps}"
    assert len(pdf_stems) > 0, "Empty PDF manifest"

def test_snapshot_count_nonzero():
    snaps = list(SNAPSHOT_DIR.glob('*.json'))
    assert len(snaps) >= 27, f"Snapshot count {len(snaps)} below baseline of 27"
```

**Verify:**
```bash
.venv/bin/pytest tests/test_manifest_consistency.py -v 2>&1 | tail -10
```
Expected: 2 tests PASS.

Commit:
```bash
git add tests/test_manifest_consistency.py
git commit -m "test(manifest): hard 1:1 PDF↔snapshot invariant in default CI"
```

### Step 4: Snapshot equality test (parametric over manifest)

Write `tests/test_v0_1_0_snapshot.py`:

```python
import json, pytest
from pathlib import Path
from fedresearch_dictionary_extractor.core.analyzer import analyze_pdf

SNAPSHOT_DIR = Path(__file__).parent.parent / 'validation_set' / 'v0.1.0_snapshot'
PDF_DIR = Path(__file__).parent.parent / 'validation_set' / 'pdfs'
NONDETERMINISTIC_FIELDS = frozenset(['extraction_timestamp'])

# Parametric over PDFs (the manifest source of truth, NOT snapshots).
# This way, a PDF without a snapshot triggers a hard failure (file-not-found),
# not a silent skip.
ALL_PDFS = sorted(PDF_DIR.glob('*.pdf'))

@pytest.mark.parametrize('pdf_path', ALL_PDFS, ids=lambda p: p.stem)
def test_snapshot_equality(pdf_path):
    snapshot_path = SNAPSHOT_DIR / f"{pdf_path.stem}.json"
    assert snapshot_path.exists(), (
        f"Missing snapshot for {pdf_path.name}; "
        f"manifest violation. Re-run scripts/regenerate_snapshot.py."
    )
    actual = analyze_pdf(str(pdf_path), profile='army')
    for f in NONDETERMINISTIC_FIELDS:
        actual.pop(f, None)
    expected = json.loads(snapshot_path.read_text())
    for f in NONDETERMINISTIC_FIELDS:
        expected.pop(f, None)
    assert actual == expected, (
        f"Snapshot drift for {pdf_path.stem}. "
        f"Re-baseline via scripts/regenerate_snapshot.py and review the diff."
    )
```

**Verify:**
```bash
.venv/bin/pytest tests/test_v0_1_0_snapshot.py -v 2>&1 | tail -15
.venv/bin/pytest tests/test_v0_1_0_snapshot.py --collect-only -q | grep -c "test_snapshot_equality"
```
Expected: all PASS; collected count == N_PDFS (27).

Commit:
```bash
git add tests/test_v0_1_0_snapshot.py
git commit -m "test(snapshot): parametric v0.1.0 oracle (default CI, full-manifest coverage)"
```

### Step 5: Inverse check on snapshot test

Modify one snapshot file by hand to confirm the test detects drift.

```bash
.venv/bin/python -c "
import json
from pathlib import Path
p = sorted(Path('validation_set/v0.1.0_snapshot').glob('*.json'))[0]
d = json.loads(p.read_text())
d['__test_drift_marker'] = True
p.write_text(json.dumps(d, indent=2, sort_keys=True))
"
.venv/bin/pytest tests/test_v0_1_0_snapshot.py -v 2>&1 | tail -10
```

**Verify:** at least one parametric test FAILS with "Snapshot drift" message.

```bash
git checkout -- validation_set/v0.1.0_snapshot/
.venv/bin/pytest tests/test_v0_1_0_snapshot.py 2>&1 | tail -5
```
**Verify:** all green again.

### Step 6: Auto-baseline measurement script

Write `scripts/measure_auto_baseline.py`. Two modes:

**`--self-test` mode:** asserts slicing contract on 5+ exemplar rows. Picks rows from at least 3 distinct docs; for each, looks up the candidate-output entry by `(doc, term)`, asserts `extractor.definition[:80] == tsv.definition_80`. Exits non-zero on any mismatch.

```python
EXEMPLAR_ROWS = [
    ('FM 4-1', 'sustainment warfighting function'),
    ('FM 3-55', 'surveillance'),
    ('AR 135-100', 'USF'),
    ('ATP 4-35', 'stability operation'),
    ('AR 12-15', 'healthcare'),
]  # picked from across 5 distinct docs, all 'g' in auto_guess

def self_test():
    """Codex iter-2 #5: contract test on 5 rows, not 1."""
    candidates = load_candidates()
    tsv_rows = load_tsv()
    for doc, term in EXEMPLAR_ROWS:
        tsv_row = next((r for r in tsv_rows if r.doc == doc and r.term == term), None)
        assert tsv_row, f"Exemplar missing from TSV: {(doc, term)}"
        cand = candidates.get(_normalize_pub(doc))
        assert cand, f"Candidate output missing for {doc}"
        match = next((e for e in cand['entries'] if e['term'] == term), None)
        assert match, f"Term not found in {doc} candidate-output: {term!r}"
        actual = match['definition'][:80]
        assert actual == tsv_row.definition_80, (
            f"Slicing contract violated for ({doc}, {term!r}): "
            f"expected {tsv_row.definition_80!r}, got {actual!r}"
        )
    print(f"Slicing contract verified on {len(EXEMPLAR_ROWS)} exemplar rows.")
```

**Default mode:** measures + writes JSON + MD. Includes invalid-baseline branch:

```python
def main():
    candidates = load_candidates()
    tsv_rows = load_tsv()
    metrics = compute_metrics(candidates, tsv_rows)

    # Invalid-baseline branch (Codex iter-2 #4)
    G_THRESHOLD_PCT = 50.0
    UNMATCHED_PAIR_LIMIT = 100
    if metrics['overall']['g_match_rate'] < G_THRESHOLD_PCT or \
       metrics['overall']['unmatched_total'] > UNMATCHED_PAIR_LIMIT:
        metrics['baseline_status'] = 'UNUSABLE'
        write_unusable_marker(metrics)
        print('WARNING: baseline UNUSABLE — see validation_set/auto_baseline_v0.1.0.UNUSABLE.txt', file=sys.stderr)
    else:
        metrics['baseline_status'] = 'USABLE'

    write_baseline_json(metrics)
    write_baseline_md(metrics)
```

Run script:
```bash
.venv/bin/python scripts/measure_auto_baseline.py --self-test
.venv/bin/python scripts/measure_auto_baseline.py
```

**Verify:**
- `--self-test` exits 0 with "Slicing contract verified on 5 exemplar rows."
- Default run produces `auto_baseline_v0.1.0.json` and `.md`
- Given planning audit (468/698 = 67% g match), baseline_status should be USABLE (above 50% threshold) but the unmatched count (230 + 159 = 389) exceeds 100 threshold → status is UNUSABLE; UNUSABLE marker file created
- Markdown clearly states the unusable status

```bash
.venv/bin/python scripts/measure_auto_baseline.py 2>&1 | tail -3  # idempotency check
diff validation_set/auto_baseline_v0.1.0.json /tmp/run1.json  # should be no diff
```

Commit:
```bash
git add scripts/measure_auto_baseline.py validation_set/auto_baseline_v0.1.0.{json,md}
[ -f validation_set/auto_baseline_v0.1.0.UNUSABLE.txt ] && git add validation_set/auto_baseline_v0.1.0.UNUSABLE.txt
git commit -m "feat(baseline): auto-classifier informational baseline with invalid-baseline branch

Reports g_emit_rate / b_emit_rate using auto_guess column;
NOT hand-vetted ground truth. Threshold check (g_match_rate < 50% OR
unmatched_pairs > 100) trips UNUSABLE marker; subsequent units must
check baseline_status before consuming metrics.

Slicing contract self-tested on 5 exemplar rows from 5 distinct docs."
```

### Step 7: README + Existing-suite check

Update README with Validation Oracles section.

```bash
.venv/bin/pytest tests/ -v 2>&1 | tail -15
```
**Verify:** existing tests pass; new tests included; total count includes 27 snapshot + 2 manifest tests.

```bash
.venv/bin/pytest tests/test_v0_1_0_snapshot.py --collect-only -q | grep -c "test_snapshot_equality"
```
**Verify:** 27.

```bash
git add README.md
git commit -m "docs(readme): document validation oracle infrastructure"
```

### Step 8: PR + merge

```bash
git push -u origin feat/2026-04-26-labels-pending-oracle
gh pr create --title "feat(oracle): v0.1.0 snapshot regression + auto-classifier baseline [Unit 1 of v0.2.0]" --body "..."
# Wait for CI
gh pr merge --squash --delete-branch
```

**Verify:** PR merged. Capture merge SHA.

## 12. Codex iter-1 + iter-2 closure (operationalized — Codex iter-2 #5)

| Finding | Resolution | Operationalized by |
|---|---|---|
| iter-1 #1 | TSV is auto-classifier; explicit | §1, §2.2 explicit framing; UNUSABLE branch in §2.2 |
| iter-1 #2 | Corpus mismatch surfaced as metric | §2.2 reports `not_in_output` per doc; threshold trips UNUSABLE |
| iter-1 #3 | Slicing contract defined | §4 codifies; Step 6 `--self-test` asserts on 5 rows |
| iter-1 #4 | Default-CI inclusion | §2.1 has no `validation` marker; Step 7 verifies via collect-only |
| iter-1 #5 | Machine-readable JSON snapshot | §2.1 IS the JSON; baseline JSON for §2.2 |
| iter-2 #1 | Manifest 1:1 invariant | §3 defined; `tests/test_manifest_consistency.py` enforces |
| iter-2 #2 | Full-corpus determinism audit | Step 1 audits all 27 PDFs; frozen exclusion list |
| iter-2 #3 | No file-vs-file fallback | §4 explicit "no fallback to substituting away extraction" |
| iter-2 #4 | Invalid-baseline branch | §2.2 + Step 6 implementation; UNUSABLE marker file |
| iter-2 #5 | Closures operationalized | This table maps every closure to a test/script/commit |
