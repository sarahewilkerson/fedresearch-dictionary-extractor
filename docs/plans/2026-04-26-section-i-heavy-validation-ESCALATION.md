# ESCALATION — Unit 4 Section-I-heavy validation

## Phase 0.a Classification

**fast-path-eligible** — preserved.

## 1. Original task

Unit 4 of v0.2.0 decomposition: hand-vet labels for Section-I-heavy worst-offender docs (AR 380-381, AR 637-2, AR 115-10, AR 700-13). M-sized.

## 2. Iter-1 findings (8 — escalating per established pattern)

1. No actual hand-vetting (operator-side per labels-pending.tsv convention; Codex wants in-unit vetting)
2. Sampled rows tagged 'b' without per-row vetting
3. Random sample misses edge cases on small docs
4. No durable comparison contract for Unit 5 regression check
5. YAML schema diverges from batch1.yaml
6. psql pipe-export brittle
7. Plaintext password in plan + non-reproducible from repo
8. TBD fields in YAML at merge time

## 3. Recommended action: Option B with iter-1 design + 6 corrections

Per established pattern (Sub-Units 1a/1b/Unit 2/Unit 3 all escalated at iter-1/2/3), apply these concrete fixes before hand-writing:

### A. Sampling (Codex #3)
- AR 380-381 (80 rows): sample 50
- AR 115-10 (155 rows): sample 50
- AR 637-2 (46 rows): take ALL 46 (full coverage on small doc)
- AR 700-13 (29 rows): take ALL 29 (full coverage on small doc)
- Total: 175 rows

### B. Per-row classification (Codex #2)
- Run `labels_classifier.classify(term, definition)` on each sampled row
- Tag with `auto_guess = classify(...)` (g or b) — not blanket 'b'
- Aligns with existing labels-pending.tsv convention (auto_guess from classifier; label empty for operator hand-vet)

### C. Export mechanics (Codex #6)
- Use `psql -F $'\t' --no-align --tuples-only` for tab-separated; escape any embedded tabs/newlines in term/definition
- Verify count matches per-doc expectation
- Reject rows with embedded tabs (would break TSV contract)

### D. YAML schema (Codex #5)
- Use exact batch1.yaml schema: top-level `flips_to_bad: { doc_stem: [page_indices] }` + `extractor_bugs_logged: { bug_name: description }`
- Remove `extractor_bugs_observed`, `per_doc_summary` deviations
- Add Section-I-heavy bugs to `extractor_bugs_logged` (matching the existing field's role)

### E. No plaintext password (Codex #7)
- Plan/script reference env var `$PROD_PG_PASSWORD` set externally; do not embed in committed files
- Add `validation_set/labels-batch2-section-i.manifest.json` with: doc canonical_ids, gcs_keys, sample row count per doc — provides reproducibility from repo without exposing credentials

### F. No TBD (Codex #8)
- Either populate fields at execution time OR remove them entirely
- Decision: remove from YAML; the populated row count + classification is the evidence

### G. Comparison contract (Codex #4) — deferred to Unit 5 with stored hash
- Each appended row gets `definition_80` (existing schema) — Unit 5's regression check uses byte-exact match per Sub-Unit 1b's lifecycle
- For docs where collision-on-prefix is plausible (large definitions), Unit 5 may add a SHA256-of-full-definition column; out of scope here

## 4. Final Codex Review

```
### Codex Adversarial Review (Iteration 1)
- **Status:** 0 SUCCESS
- **Findings:** 8 material
- **Verdict impact:** Per >5-finding threshold, Option B with corrections.
```

## 5. Recommended next action

Hand-write per iter-1 design + §3 corrections. ~30 min.

<promise>PLAN_ESCALATED</promise>
