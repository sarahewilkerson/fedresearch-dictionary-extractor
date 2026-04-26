# Sub-Unit 1b — batch1 reconciliation + corpus-pin test

## Phase 0.a Classification

**fast-path-eligible** — small YAML data file + parametric pytest, single repo, fully reversible.

## 1. Problem statement

`labels-batch1.yaml` records 5 hand-flips from a 2026-04-22 user spot-check. Two of those flips are unambiguously resolvable against current `validation_set/candidate-output/`: TC_1-19.30 idx 1 (page-footer bleed) and FM_3-34 idx 4 (asterisk-prefix split). The other 3 cannot be cleanly mapped (provenance drift). Capture the 2 unambiguous ones as concrete `(doc, term, definition_prefix_80)` triples, document the 3 unresolvable cases honestly, and add a corpus-pin test that fails when the committed candidate-output JSONs no longer contain those known-bad pairs (which is what happens when Unit 3 regenerates candidate-output under a fixed extractor).

## 2. Scope honesty (Codex iter-1 #1)

**This is a corpus pin, not an extractor regression test.** It verifies that committed `candidate-output/*.json` files still contain the known-bad pairs. It does NOT exercise the extractor binary. The protection it provides downstream is: Unit 3's plan must regenerate candidate-output as part of shipping the fix; when that happens, this corpus-pin test fails and the fix's PR must update both the YAML (or remove the file) and the test (or invert it).

The naming reflects this: `test_v0_1_0_corpus_pin_emits_known_forbidden_pairs`.

## 3. Reconciliation results (verified at planning time)

Content-matched against current candidate-output. Final disposition:

### forbidden_pairs (2) — index stable + bug pattern unambiguous

- **TC 1-19.30 entries[1]:** `term="dampen \nusually"`. Page-footer bleed pattern; embedded newline; matches `page_footer_in_entries`.
- **FM 3-34 entries[3]:** `term="*field"`. Asterisk-prefix split pattern; matches `asterisk_term_split`.

### unresolvable_flips (3) — provenance drift; cannot pin

- **AR 190-55 idx 5:** entries 0-16 all legitimate (acronym→expansion list + 4 multi-word terms). Original flip target irrecoverable.
- **AR 12-15 idx 2:** entries 0-7 inspected. Idx 2 candidates (entries[1]=`USMC`, entries[2]=`USN`) are legitimate. **However, entries[6] (`WHINSEC`) has trailing body-text contamination ("This section contains entr...") and entries[7] (`healthcare`) has a fragment definition** — these are suspect but not at the flipped index. Documented as unresolved-with-suspect-candidates; not pinned.
- **ADP 3-07 idx 8:** out of bounds (current doc has 7 entries). Multiple current entries look bad (`*reintegration` matches asterisk pattern; `security`/`stability`/`unified`/`unity` look like multi-word term splits). Cannot pick one without original spot-check notes. Documented as unresolved.

Final pinned set: **2 pairs from 2 docs.**

## 4. Approach

### 4.1 `validation_set/batch1_reconciled.yaml`

Hand-written. Schema:

```yaml
# Source: labels-batch1.yaml (2026-04-22 user spot-check) reconciled to
# current candidate-output by content-matching against extractor_bugs_logged
# patterns. Generated 2026-04-26 per Sub-Unit 1b plan.
#
# This is a CORPUS PIN, not an extractor regression test. See
# docs/plans/2026-04-26-batch1-reconciliation.md §2.

forbidden_pairs:
  - doc: TC 1-19.30
    term: "dampen \nusually"
    definition_prefix_80: "<exact 80-char prefix from current candidate-output>"
    bug_pattern: page_footer_in_entries
    source_batch1_idx: 1
    candidate_output_idx: 1   # 0-based in current JSON

  - doc: FM 3-34
    term: "*field"
    definition_prefix_80: "force engineering The application of Army engineering capabilities fro"  # placeholder; verified at execution
    bug_pattern: asterisk_term_split
    source_batch1_idx: 4
    candidate_output_idx: 3

unresolvable_flips:
  - doc: AR 190-55
    source_batch1_idx: 5
    note: All 17 entries in current candidate-output are legitimate; original flip target irrecoverable.
  - doc: AR 12-15
    source_batch1_idx: 2
    note: |
      Entries[1]=USMC and entries[2]=USN at the flipped index look legitimate.
      However, entries[6] (WHINSEC) has trailing body-text contamination
      ("This section contains entr...") and entries[7] (healthcare) has a
      fragment definition. Suspect candidates exist at non-flipped indices;
      original flip target cannot be pinned without source notes.
  - doc: ADP 3-07
    source_batch1_idx: 8
    note: |
      Original idx 8 is out of bounds (current doc has 7 entries). Multiple
      bad-looking candidates exist (entries[1]='*reintegration' matches asterisk
      pattern; entries[2/3/5/6] look like multi-word term splits). Cannot pin
      to one without original spot-check notes.
```

### 4.2 `tests/test_batch1_reconciled.py`

```python
"""Corpus pin against committed candidate-output JSONs (Sub-Unit 1b).

This test verifies that committed candidate-output/*.json files still contain
known-bad (term, definition_prefix_80) pairs reconciled from labels-batch1.yaml.
It is NOT an extractor regression test — it does not invoke the extractor.

Lifecycle: when Unit 3 fixes the extractor and regenerates candidate-output,
this test fails. The fix's PR must either:
  (a) update batch1_reconciled.yaml to a new corpus pin, OR
  (b) flip the assertion to `not in actual` (extractor no longer emits the
      known-bad pair), OR
  (c) delete this file (oracle replaced by extractor-level tests in Unit 3).
"""
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent / "validation_set"
RECONCILED = ROOT / "batch1_reconciled.yaml"
CANDIDATE_OUTPUT = ROOT / "candidate-output"

def _load_pairs():
    return yaml.safe_load(RECONCILED.read_text())["forbidden_pairs"]

def _load_candidate(doc: str) -> dict:
    """Find the single candidate-output JSON for `doc` (matches source_pub_number,
    with DA PAM ↔ PAM normalization). Asserts exactly one match (Codex iter-1 #5).
    """
    target_normalized = doc
    target_da_pam = (
        doc.replace("PAM ", "DA PAM ", 1)
        if doc.startswith("PAM ") and not doc.startswith("DA PAM ")
        else doc
    )
    matches = []
    for j in CANDIDATE_OUTPUT.glob("*.json"):
        try:
            d = json.loads(j.read_text())
        except json.JSONDecodeError:
            continue
        pub = d.get("source_pub_number")
        if pub in (target_normalized, target_da_pam):
            matches.append((j.name, d))
    assert len(matches) == 1, (
        f"Expected exactly 1 candidate-output JSON for doc={doc!r}, "
        f"found {len(matches)}: {[m[0] for m in matches]}"
    )
    return matches[0][1]

@pytest.mark.parametrize(
    "pair", _load_pairs(),
    ids=lambda p: f"{p['doc'].replace(' ', '_')}__{p['term'][:20].strip()}",
)
def test_v0_1_0_corpus_pin_emits_known_forbidden_pair(pair):
    out = _load_candidate(pair["doc"])
    forbidden = (pair["term"], pair["definition_prefix_80"])
    actual = {(e["term"], e["definition"][:80]) for e in out["entries"]}
    assert forbidden in actual, (
        f"Corpus pin broken: {pair['doc']} no longer emits forbidden pair "
        f"{forbidden!r}. This may signal:\n"
        f"  (a) candidate-output was regenerated under a fixed extractor "
        f"(intended outcome — flip assertion or update YAML),\n"
        f"  (b) candidate-output drift unrelated to extractor fix "
        f"(investigate before updating)."
    )
```

## 5. Hard 30%

- **Test framing** (Codex iter-1 #1, #2): explicitly named and documented as a corpus pin. Lifecycle baked into the docstring.
- **Uniqueness assertion in `_load_candidate`** (Codex iter-1 #5): exactly-one-match required; loud failure otherwise.
- **2 pinned pairs** (Codex iter-1 #3, #4): conservative — only docs where index AND content are unambiguously stable. Drops ADP from forbidden_pairs and adds it to unresolvable.
- **Exact `definition_prefix_80` capture**: at execution time, not from memory. Step 1 verifies.
- **Lifecycle ownership**: §2 documents that Unit 3 owns the next state transition (regenerate corpus / flip assertion / delete oracle).

## 6. Blast radius

- 2 new files (`validation_set/batch1_reconciled.yaml`, `tests/test_batch1_reconciled.py`); 0 modified.
- Default-CI test, not behind `validation` marker.
- Failure mode is self-explanatory (assertion message names doc + pair + lifecycle options).
- Risk: low. If the corpus pin breaks for unintended reasons (drift unrelated to fix), the assertion message guides investigation.

## 7. Verification

1. **Capture exact `definition_prefix_80` values from current candidate-output:**
   ```bash
   /Users/mw/code/fedresearch-dictionary-extractor/.venv/bin/python - <<'PY'
   import json, glob
   targets = [
       ('TC_1-19.30', 1, 'dampen \nusually'),
       ('FM_3-34', 3, '*field'),
   ]
   for prefix, idx, expected_term in targets:
       j = glob.glob(f'/Users/mw/code/fedresearch-dictionary-extractor/validation_set/candidate-output/{prefix}*.json')[0]
       d = json.load(open(j))
       e = d['entries'][idx]
       assert e['term'] == expected_term, f"Term drift: expected {expected_term!r}, got {e['term']!r}"
       print(f"{prefix} idx {idx}: term={e['term']!r}")
       print(f"  def[:80]={e['definition'][:80]!r}")
   PY
   ```
   Expected: 2 (term, def[:80]) outputs verified.

2. **Test passes:**
   ```bash
   .venv/bin/pytest tests/test_batch1_reconciled.py -v
   ```
   Expected: 2 PASS.

3. **Uniqueness assertion fires correctly:**
   ```bash
   # Inject a test scenario where doc has 2 matching JSONs to confirm assertion
   cp validation_set/candidate-output/TC_1-19.30*.json /tmp/_dup.json.bak
   cp validation_set/candidate-output/TC_1-19.30*.json validation_set/candidate-output/_DUP_FOR_TEST.json
   .venv/bin/pytest tests/test_batch1_reconciled.py -v 2>&1 | tail -10
   rm validation_set/candidate-output/_DUP_FOR_TEST.json
   ```
   Expected: with duplicate, test FAILS with "Expected exactly 1...found 2" message; after cleanup, passes again.

4. **Existing test suite regression:**
   ```bash
   .venv/bin/pytest tests/ 2>&1 | tail -5
   ```
   Expected: green.

5. **Default CI inclusion check:**
   ```bash
   .venv/bin/pytest tests/test_batch1_reconciled.py --collect-only -q
   ```
   Expected: 2 tests collected (no marker filter required).

## 8. Documentation impact

- `validation_set/batch1_reconciled.yaml` (new — data deliverable)
- `tests/test_batch1_reconciled.py` (new — assertion deliverable, with framing in docstring)
- README rewrite is Sub-Unit 1c's job; out of scope here.

## 9. Completion criteria

1. `validation_set/batch1_reconciled.yaml` exists with **2** `forbidden_pairs` (TC 1-19.30, FM 3-34) and **3** `unresolvable_flips` (AR 190-55, AR 12-15 with WHINSEC/healthcare suspect notes, ADP 3-07 with idx-OOB note).
2. Each `forbidden_pairs` entry has the exact `definition_prefix_80` captured from current candidate-output (verified by Step 1 of §7).
3. `tests/test_batch1_reconciled.py` exists with:
   - Module docstring documenting corpus-pin framing + lifecycle.
   - `_load_candidate` asserting exactly one match (Codex #5).
   - 2 parametric `test_v0_1_0_corpus_pin_emits_known_forbidden_pair` tests passing.
4. Uniqueness assertion verified to fire correctly under duplicate-JSON test (§7 step 3).
5. Default `pytest tests/` continues green.
6. Test collected by default CI (no `@pytest.mark.validation`).

## 10. Execution sequence

### Step 1: Capture exact `definition_prefix_80`

Run §7 step 1.

**Verify:** 2 outputs with verified term values; no drift.

### Step 2: Write `validation_set/batch1_reconciled.yaml`

Per §4.1. Insert exact `definition_prefix_80` values from Step 1.

**Verify:**
```bash
.venv/bin/python -c "
import yaml
d = yaml.safe_load(open('validation_set/batch1_reconciled.yaml'))
print(f'forbidden_pairs: {len(d[\"forbidden_pairs\"])}')
print(f'unresolvable_flips: {len(d[\"unresolvable_flips\"])}')
"
```
Expected: `forbidden_pairs: 2`, `unresolvable_flips: 3`.

### Step 3: Write `tests/test_batch1_reconciled.py`

Per §4.2.

**Verify:**
```bash
.venv/bin/pytest tests/test_batch1_reconciled.py -v 2>&1 | tail -10
```
Expected: 2 PASS.

### Step 4: Verify uniqueness assertion

Per §7 step 3.

**Verify:** test fails under duplicate JSON; passes after cleanup.

### Step 5: Existing-suite regression

```bash
.venv/bin/pytest tests/ 2>&1 | tail -5
```
Expected: green.

### Step 6: Commit

```bash
git add validation_set/batch1_reconciled.yaml tests/test_batch1_reconciled.py
git commit -m "feat(oracle): batch1 reconciled + corpus-pin test [plan: 2026-04-26-batch1-reconciliation]"
```

(PR + CI + merge handled by Phase 6 Sync & Close.)
