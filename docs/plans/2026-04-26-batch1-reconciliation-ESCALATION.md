# ESCALATION — Sub-Unit 1b batch1 reconciliation

## Phase 0.a Classification

**fast-path-eligible** — preserved from source plan.

## 1. Original task

Sub-Unit 1b of v0.2.0 decomposition: reconcile `labels-batch1.yaml`'s 5 hand-flips against current candidate-output, capture concrete forbidden pairs in YAML, add a strict pytest regression test using pinned candidate-output JSONs (no PDF re-extraction). XS-sized, ~45 minutes.

## 2. Attempts summary

### Iter-1 (5 Codex findings)
Test framing as corpus-pin not extractor regression; lifecycle ambiguity for the baseline-pin; ADP 3-07 reconciliation under-justified (idx 8 OOB); AR 12-15 has suspect entries not noted; `_load_candidate` uniqueness assertion missing.

### Iter-2 (7 Codex findings — increased)
Uniqueness model rigor (real publication-name variants beyond DA PAM); lifecycle decision rule for Unit 3 (which of update/flip/delete is correct under which condition); ADP downgrade standard (when to refuse pinning); AR 12-15 followup obligation for documented suspects; pinned-pair uniqueness within doc + prefix discriminativeness proof; fixture-based failure testing instead of mutating live corpus; CI ownership for sentinel-test failures.

## 3. Persistent failure

Same pattern as Sub-Unit 1a's escalation: `/review-plan` applies rigor proportional to "load-bearing tool" rather than to the task's actual scope (~5 lines of YAML + ~50 lines of test). Each iteration adds rigor surface area faster than the deliverable warrants. Iter-1 → iter-2 trajectory increased (5 → 7), confirming non-convergence.

The iter-2 findings are individually valid — they describe a more rigorous artifact than this XS task scopes for. They are not correctness-blocking; the plan-as-written would produce a working YAML + test that delivers the small value it claims (a corpus pin flagging when candidate-output is regenerated under a fixed extractor). The findings request more rigorous artifacts: load-bearing decision rules, exhaustive failure-mode testing, fixture-based isolation, downstream ownership specifications.

## 4. Final Codex Adversarial Review

```
### Codex Adversarial Review (Iteration 2)
- **Status:** 0 SUCCESS
- **Findings:** 7 material
  #1: Uniqueness model under-realistic; needs fixture-based proof
  #2: Lifecycle decision rule for Unit 3 ambiguous (update/flip/delete)
  #3: ADP 3-07 downgrade standard not specified
  #4: AR 12-15 documented suspects need followup obligation
  #5: Pinned pair uniqueness + prefix discriminativeness unproven
  #6: Failure-test mutates live corpus; should use fixtures
  #7: Default CI sentinel test lacks ownership specification
- **Verdict impact:** Trajectory 5 → 7. Not converging. Per
  feedback_review_iter_cap_convergence_judgment.md, does not qualify
  for operator-judgment APPROVED via convergence trajectories.
```

## 5. Why escalate at iter-2 (not iter-3)

Sub-Unit 1a established the pattern: iter-3 produced 8 more findings (8 → 7 → 8 trajectory) and required escalation anyway. Burning iter-3 here predicts the same outcome — more rigor findings, no convergence. Pre-emptive escalation honors the user's stated priority ("get this resolved") without wasting another review cycle on the same miscalibration pattern.

## 6. Recommended next approach: Option B (parallel to 1a)

The user previously approved this exact pattern for Sub-Unit 1a:

1. **Drop the iter-2 plan.** It works, but the next round of plan-review will demand more rigor, and we've established that pattern doesn't converge for XS tasks.
2. **Hand-write the deliverable directly:**
   - `validation_set/batch1_reconciled.yaml` with 2 forbidden_pairs (TC, FM) + 3 unresolvable_flips (AR 190-55, AR 12-15 with suspect notes, ADP 3-07 with idx-OOB note).
   - `tests/test_batch1_reconciled.py` with module-docstring framing as corpus-pin, parametric test, uniqueness assertion in `_load_candidate`.
3. **Acknowledge known-good-enough rigor.** The corpus-pin nature + lifecycle ownership + uniqueness assertion are enough for the deliverable's actual value (signal corpus regeneration when extractor is fixed; defend against duplicate-JSON aliasing bugs).
4. **Track the iter-2 deferred concerns** as comments in the YAML (lifecycle decision rule for Unit 3, AR 12-15 suspect followups) rather than as separate hard plan requirements.
5. **Commit directly** with reference to this escalation as the plan trail.

## 7. Suggested rule reinforcement

The CLAUDE.md rule suggestion from Sub-Unit 1a's escalation continues to apply:

> **Plan-review rigor must scale with task blast radius, not uniformly across task sizes.** A fast-path-eligible XS task with low operational risk should pass with proportionally light criteria. If `/review-plan` returns >5 material findings on an XS task across 2 iterations, that is signal the rigor is miscalibrated for the task scope — either downgrade to "no plan needed" (commit-with-justification) or scale rigor down. Don't iterate to convergence on rigor that exceeds the task's blast radius.

This sub-unit confirms the pattern: 5 findings iter-1 + 7 findings iter-2 = 12 across 2 iterations on an XS task. The threshold from the rule fires here. Escalating early per its guidance.

---

**Plan file path:** `docs/plans/2026-04-26-batch1-reconciliation.md` (iter-2 plan, retained for reference).

**Recommended next action:** drop the script-based plan-review path; hand-write `validation_set/batch1_reconciled.yaml` + `tests/test_batch1_reconciled.py` directly with the iter-2 design (which addresses iter-1's 5 findings comprehensively). Commit directly. ~30 min total.

<promise>PLAN_ESCALATED</promise>
