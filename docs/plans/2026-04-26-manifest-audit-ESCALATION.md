# ESCALATION — Sub-Unit 1a manifest audit

## Phase 0.a Classification

**fast-path-eligible** — preserved from the source plan: read-only audit script + Markdown report, single repo, fully reversible.

## 1. Original task

Sub-Unit 1a of the v0.2.0 decomposition (per Unit 1's escalation): write a re-runnable Python script that audits `validation_set/`'s corpus state and emits `validation_set/manifest_audit.md`. Pure data clarity for downstream sub-units (1b, 1c, Unit 4). XS-sized, ~30 minutes.

## 2. Attempts summary

### Iter-1 (8 Codex findings)
Bidirectional reconciliation; precise stem normalization; structural vs snapshot acceptance; stdout vs file-write contract; targeted spot checks; schema-drift fail-loud; calibrated blast radius; technical-acceptance vs delivery separation.

### Iter-2 (7 Codex findings — decreasing)
Cardinality rules for ambiguous matches; duplicate / conflict detection across artifacts; deeper schema validation (per-JSON `source_pub_number`); atomic write semantics; machine-checkable verification; full schema-failure tests for all 3 artifacts (manifest / TSV / batch1 yaml); git-rev-only header for determinism.

### Iter-3 (8 Codex findings — back up)
Acceptance criteria don't require core sections; label-doc cardinality underspecified; duplicate-detection negative tests don't cover all duplicate types; atomic-write spec doesn't cover write-path failure or temp-file cleanup; git-rev header doesn't handle non-git/dirty-tree; schema-failure tests don't cover candidate-output JSON; snapshot vs invariant assertions mixed; severity thresholds for conflicts undefined.

## 3. Persistent failure

**Same pattern as Unit 1's escalation:** every iteration adds rigor surface area (new failure modes to test, new edge cases to specify, new acceptance criteria to enforce). For a 150-line audit script, three rounds of plan-review have produced a 250+ line plan that's still flagged with material gaps. The trajectory is not converging.

The findings are individually valid. Collectively they describe a much larger task than the original "XS, ~30 min" framing intended.

## 4. Final Codex Adversarial Review

```
### Codex Adversarial Review (Iteration 3)
- **Status:** 0 SUCCESS
- **Findings:** 8 material
  #1: Acceptance criteria don't require core report sections from §4
  #2: Label-doc cardinality model underspecified
  #3: Duplicate-detection negative tests too narrow
  #4: Atomic-write doesn't specify write-path failure / temp cleanup
  #5: Git-rev header has unaddressed non-git / dirty-tree operational cases
  #6: Schema-failure coverage skips candidate-output JSON
  #7: Snapshot vs invariant assertions mixed in §9
  #8: Severity thresholds for conflicts undefined
- **Verdict impact:** Findings trajectory 8 → 7 → 8. Not monotonically
  decreasing. Surface widening. Per
  feedback_review_iter_cap_convergence_judgment.md, does not qualify
  for operator-judgment APPROVED at iter-3 cap.
```

## 5. Blocking question for human

**The audit data already exists in this conversation.** It was gathered during planning:

- 30 PDFs in `validation_set/pdfs/`: 27 well-formed `.pdf`, 1 truncated `.p`, 2 extensionless
- 27 `.json` files in `validation_set/candidate-output/` plus `NO_DEFINITIONS.txt`
- 19 unique docs in `labels-pending.tsv` (866 rows, label column empty, auto_guess: 698 g / 168 b)
- 5 `flips_to_bad` entries in `labels-batch1.yaml` (TC_1-19.30, AR_190-55, ADP_3-07, AR_12-15, FM_3-34)
- 3 docs need `DA PAM ↔ PAM` normalization (PAM 190-45, PAM 350-58, PAM 71-32)
- Corpus byte-exact match audit: 468/698 g rows + 9/168 b rows match current candidate-output

**The information is the deliverable.** The script is just a way to regenerate it. For Sub-Units 1b / 1c / Unit 4, having this information committed in a Markdown file is enough.

**Three options:**

- **A) Operator-judgment APPROVED for the iter-3 plan.** Acknowledge remaining gaps (label cardinality, atomic-write edge cases, etc.) as "v2 follow-up if the audit script ever needs to be a load-bearing tool." Ship the script + report; gaps are tracked for a future sub-unit if the corpus changes meaningfully.

- **B) Drop the script entirely; commit a hand-written `validation_set/manifest_audit.md`.** Use the data I already have. ~10 minute task. No script means no script-rigor gaps. If the corpus changes later, regenerate by hand or write a script then.

- **C) Skip Sub-Unit 1a entirely; fold its data inline into Sub-Unit 1c's README rewrite.** The corpus-state information becomes a section of the README; Sub-Units 1b / Unit 4 cite the README. Saves ~30 min of plan/execute/review.

## 6. Recommended next approach

**Option B: hand-written audit doc.** Reasons:

1. **The data IS the deliverable.** The script's value is regeneration; for an XS task, regeneration is a marginal future convenience.
2. **Plan-review rigor matches the script's rigor target.** The script would have been correct enough; plan-review wants rigor proportional to the script being a long-term canonical tool, which is more than this task scopes.
3. **The user's directive ("get this resolved") is satisfied directly** by writing the doc, not by writing a script that writes the doc.
4. **Sub-Units 1b / 1c / Unit 4 just need the information.** A hand-written doc serves them as well as a generated one.

Concretely: skip the script in this sub-unit. Commit a hand-written `validation_set/manifest_audit.md` directly. If a script becomes load-bearing later (e.g., Unit 4 wants automated re-audits), spin up a separate sub-unit then with appropriate scope.

## 7. Suggested rule for `~/.claude/CLAUDE.md`

Two iterations of /develop on this v0.2.0 work have escalated for the same reason: plan-review's rigor floor is too high relative to fast-path-eligible XS task scope. Rigor proportional to risk is the principle but isn't operationalized in `/review-plan`.

Suggested addition under "Iterative Loop Discipline" or as a new "Plan Review Rigor Calibration" section:

> **Plan-review rigor must scale with task blast radius, not run uniformly across task sizes.** A fast-path-eligible XS task with low operational risk should pass plan-review with proportionally light criteria — not the same rigor floor applied to a full-flow architectural change. If `/review-plan` returns >5 material findings on an XS task across 2 iterations, that is signal that either the task should be downgraded to "no plan needed" (commit-with-justification flow) OR the rigor expectation is miscalibrated for the task scope. Don't iterate to convergence on rigor that exceeds the task's blast radius.

Operator decides whether to apply.

---

**Plan file path:** `docs/plans/2026-04-26-manifest-audit.md` (iter-3 plan, retained for reference).

**Recommended next action:** drop the script-based approach; hand-write `validation_set/manifest_audit.md` directly with the data already gathered. ~10 min, no further plan review needed (it's a documentation update; treat as `[plan: 2026-04-26-manifest-audit]` reactive amendment).

<promise>PLAN_ESCALATED</promise>
