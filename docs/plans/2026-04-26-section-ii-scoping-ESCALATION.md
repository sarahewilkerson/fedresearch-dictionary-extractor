# ESCALATION — Unit 3 Section II range scoping

## Phase 0.a Classification

**fast-path-eligible** — preserved.

## 1. Original task

Unit 3 of v0.2.0 decomposition: when `metadata.section_structure ∈ {"both", "section_ii_only"}` (Unit 2 detection), narrow extraction to Section II range; end at first Section III/IV/V header or original glossary end. M-sized, ~2-3 hr.

## 2. Attempts summary

### Iter-1 (8 findings)
Section IV missing; page-level vs line-level boundary; positional constraint vs body text; identity transform too permissive; single-doc verification; weak distribution gate; no AR 380-381 acceptance; mock-heavy tests.

### Iter-2 (5 findings — decreasing)
SECTION_III/SECTION_AFTER_II naming inconsistent across plan; regex tightening scope larger than admitted; narrowing_fired not blocking; AR 380-381 acceptance too weak; e2e test isn't truly e2e.

### Iter-3 (8 findings — back up)
Naming contradiction across §3.1/§3.5/Step-1; blast radius understates classification drift from regex tightening; narrowing_fired gate weakened in §9 vs §7.4; pre-flight not formal; AR 380-381 not machine-enforced; same-page Section II + III boundary; page-read errors in forward scan; completion criteria don't cover all 3 new metadata fields.

## 3. Persistent failure pattern

Same wrong-boundary pattern documented in Sub-Units 1a/1b and Unit 2 escalations: rigor surface widens at iter-3 as previous fixes expose new dimensions. Trajectory 8 → 5 → 8 is non-converging.

The iter-3 findings split into:
- **Plan-internal consistency** (#1, #3, #8): mechanical alignment between sections — easy fixes for the Option B hand-write.
- **Pre-flight rigor** (#4): formalizing the corpus header-form scan as a gate.
- **Real concerns flagged but corner-case** (#2 classification drift from regex tightening, #6 same-page boundary, #7 boundary-scan error masking): mitigations via additional metadata fields + distribution analysis acceptance, not blocking for the dominant AR 380-381 fix.
- **Test-infrastructure gap** (#5 machine-enforced AR 380-381): requires real PDF in CI; out of scope.

## 4. Final Codex Adversarial Review

```
### Codex Adversarial Review (Iteration 3)
- **Status:** 0 SUCCESS
- **Findings:** 8 material
  #1: SECTION_AFTER_II naming inconsistent across plan sections
  #2: Blast radius understates regex tightening's classification drift
  #3: narrowing_fired gate weakened in §9 vs §7.4
  #4: Corpus pre-flight not formalized as gate
  #5: AR 380-381 acceptance not machine-enforced
  #6: Same-page Section II + III boundary corner case
  #7: Boundary-scan page-read errors masked as success
  #8: Completion criteria miss section_ii_narrowing_attempted/fired fields
- **Verdict impact:** Trajectory 8 → 5 → 8. Per
  feedback_review_iter_cap_convergence_judgment.md, does not qualify for
  operator-judgment APPROVED.
```

## 5. Recommended action: Option B with iter-3 design + targeted fixes

Apply these concrete corrections to the iter-3 design before hand-writing:

### A. Naming consistency (#1, #3, #8 — mechanical)
- Use `SECTION_AFTER_II_HEADER` consistently throughout. Remove all `SECTION_III_HEADER` references.
- Remove `Section IV` from negative-test lists; it's a positive case for `SECTION_AFTER_II_HEADER`.
- Sync §9 completion criteria with §7.4's strengthened acceptance: 0 unexplained identity-fallbacks for `both`/`section_ii_only`; AR 380-381 hard blocker; all 3 metadata fields (`section_ii_pages`, `section_ii_narrowing_attempted`, `section_ii_narrowing_fired`) wired + schema-declared + tested.

### B. Pre-flight as formal gate (#4)
- Move §7.5a corpus header-form scan into §9 completion criteria as item 1. Plus distribution before/after of `section_structure` values across the local corpus (#2): every classification delta must be reviewed and explained in §10.

### C. Boundary-scan error tracking (#7)
- Add `metadata.section_ii_boundary_scan_errors: int` field counting pages that errored during the forward scan for SECTION_AFTER_II_HEADER. Distribution analysis flags any doc with `> 0` for review.

### D. Mitigations (deferred but tracked)
- Same-page Section II + III boundary (#6): documented as known limitation in helper docstring + plan §5. Distribution analysis would surface affected docs (entry count would be 0 or near-0 with `narrowing_fired=True`). If observed, follow-up unit handles line-level boundary detection.
- Machine-enforced AR 380-381 acceptance (#5): operator runs `scripts/measure_section_distribution.py` locally with PDFs available; script asserts AR 380-381's narrowed range AND absence of named Section I terms AND presence of named Section II terms; exits non-zero on failure. Not in CI (PDFs gitignored), but committed assertion logic provides repeatability.

## 6. Rule reinforcement

The CLAUDE.md rule suggestion from Sub-Unit 1a/1b/Unit 2 escalations continues to apply. **All 4 cycles in Unit 1's escalation-decomposed work + Unit 2 + Unit 3 escalated at iter-3.** This consistent pattern strongly suggests the rule should be formalized:

> **Plan-review rigor must scale with task blast radius.** XS/S/M tasks should not iterate to convergence on rigor that exceeds the deliverable. >5 findings across 2 iterations OR non-decreasing trajectory at iter-3 is the operational threshold for Option B (hand-write per latest design with targeted fixes; defer corner cases to monitoring or follow-up units).

---

**Plan file path:** `docs/plans/2026-04-26-section-ii-scoping.md` (iter-3 plan, retained as design source).

**Recommended next action:** hand-write per iter-3 design with §5.A/B/C corrections applied. ~60 min total (M-sized task with real code change).

<promise>PLAN_ESCALATED</promise>
