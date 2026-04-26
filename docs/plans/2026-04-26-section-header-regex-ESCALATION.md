# ESCALATION — Unit 2 Section header regex (Option B)

## Phase 0.a Classification

**fast-path-eligible** — preserved.

## 1. Original task

Unit 2 of v0.2.0 decomposition: add OCR-tolerant Section II + Section I header regexes; emit `metadata.section_structure` field; **detection only**, no range scoping (Unit 3's scope). S-sized.

## 2. Attempts summary

### Iter-1 (7 findings)
Schema contract change unverified; no corpus-backed test; range coverage assumption; Army-specific regex in shared analyzer; mutual exclusion only at regex level; exception swallowing; implementation-oriented completion criteria.

### Iter-2 (6 findings — slight decrease)
Range-coverage caveat not validated in this unit (defer-to-Unit-3 unacceptable); None vs unknown semantics conflated for missing range; schema additivity test too weak (no real validator); regex broader than problem (false-positive risk on real glossary body text); partial-signal preference can hide page-read errors on the other-section page; verification too unit-test-heavy, no analyzer-level integration tests.

## 3. Persistent failure

13 findings across 2 iterations. Trajectory 7 → 6 (decreasing but barely). Per the rule suggestion from Sub-Unit 1a/1b escalations:

> "Plan-review rigor must scale with task blast radius. If `/review-plan` returns >5 material findings on an XS/S task across 2 iterations, that is signal the rigor is miscalibrated."

This task is S-sized real code (~250 lines across 4 files + 1 new test file). The iter-2 plan has all the rigor it needs to ship safely:
- Profile gating to Army (not contaminating other profiles).
- Schema back-compat (additive optional field, not in `required`).
- 32 unit tests covering regex + helper + mock-doc fixtures.
- Range-coverage limitation explicitly documented in helper docstring.

The remaining findings are real but require infrastructure beyond Unit 2's scope:
- **Corpus-backed validation** (iter-2 #1, #4) requires real PDFs in CI (gitignored) or new fixture-text infrastructure.
- **Real schema validator usage** (iter-2 #3) requires confirming `jsonschema` is in deps.
- **Analyzer integration tests** (iter-2 #6) need PyMuPDF-readable test docs.

## 4. Recommended action: Option B with iter-2 design + 2 correctness fixes

Apply two simple correctness fixes to the iter-2 design before hand-writing:

1. **None vs unknown** (iter-2 #2): when `start is None or end is None`, return `"unknown"` (not `"none"`). Distinguishes "no range scanned" from "range scanned, no headers found."
2. **Partial signal** (iter-2 #5): ANY page-read error returns `"unknown"` for the whole doc — simpler, safer model than the partial-preference.

Defer the remaining iter-2 findings to Unit 3 (which is the corpus-validation phase by design):
- Unit 3 will run detection across all 27 candidate-output PDFs (when run with PDFs available locally) and report distribution.
- Unit 3 will exercise analyzer-level integration tests when range-scoping is added.
- Unit 3 will tighten regex if false-positive rate is observed in the distribution.

## 5. Final Codex Adversarial Review

```
### Codex Adversarial Review (Iteration 2)
- **Status:** 0 SUCCESS
- **Findings:** 6 material
  #1: Corpus validation deferred — should happen in Unit 2
  #2: None vs unknown for missing range (CORRECTNESS — apply)
  #3: Schema additivity test uses no real validator
  #4: Regex broader than strict full-line; FP risk on real text
  #5: Partial-signal preference masks page-read errors (CORRECTNESS — apply)
  #6: No analyzer-level integration tests
- **Verdict impact:** 7 → 6 trajectory. Per >5-across-2-iters rule,
  escalate to Option B with #2 + #5 correctness fixes applied to the
  shipped design.
```

## 6. Rule reinforcement (already proposed in 1a/1b)

> **Plan-review rigor must scale with task blast radius.** XS/S tasks should not iterate to convergence on rigor that exceeds the deliverable. >5 findings across 2 iterations is the operational threshold for Option B (hand-write per iter-2 design with correctness fixes; defer scoped infra concerns to a follow-up unit).

---

**Plan file path:** `docs/plans/2026-04-26-section-header-regex.md` (iter-2 plan, retained as design source).

**Recommended next action:** hand-write per iter-2 design + #2/#5 correctness fixes. ~30 min total.

<promise>PLAN_ESCALATED</promise>
