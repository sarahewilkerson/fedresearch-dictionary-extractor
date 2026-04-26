# ESCALATION — Unit 1: labels-pending oracle

## Phase 0.a Classification

**fast-path-eligible** — additive test infrastructure (Unit 1 is the same scope as the labels-pending-oracle plan). Classification preserved from the original plan: single repo, fully reversible, no production touch.

## 1. Original task

Unit 1 of the v0.2.0 decomposition (`docs/plans/2026-04-26-v0.2-decomposition.md`): build automated regression oracle from `validation_set/labels-pending.tsv` (866 rows) and measure v0.1.0 baseline. No extractor logic changes. Single `/develop` cycle, S-sized.

User's stated motivation: "I previously vetted by hand a list of something like 100 definitions from a couple of regs. Why can't you use that as a verified test on your changes?"

## 2. Attempts summary

### Iteration 1 — `labels-pending.tsv` as oracle
- **Approach:** byte-exact `(term, definition[:80])` pair-match assertions on TSV rows; baseline measurement via Markdown report.
- **Codex findings (5):**
  - #1 `label` column is empty for ALL rows; `auto_guess` carries g/b — TSV is auto-classifier output awaiting human review, NOT hand-vetted.
  - #2 Corpus audit: 468/698 g and 9/168 b match current candidate-output — provenance drift between TSV and pinned JSONs.
  - #3 Byte-vs-char slicing for `definition[:80]` undefined.
  - #4 `@pytest.mark.validation` excludes from default CI; "automated regression oracle" silently rots.
  - #5 Markdown baseline isn't machine-enforced.
- **Verdict:** REVISE.

### Iteration 2 — snapshot-equality oracle + auto-baseline split
- **Approach:** strict snapshot equality test in default CI; informational auto-classifier baseline as a separate script with a `<50% match → UNUSABLE` branch.
- **Codex findings (5):**
  - #1 Coverage manifest inconsistency (19 / 27 / "in pdfs/"); `pytest.skip` on missing PDF was silent.
  - #2 Determinism audit on 1 PDF too narrow; "discover during execution" is open-ended.
  - #3 "Snapshot-of-snapshot" fallback for CI runtime defeats the oracle.
  - #4 Invalid-baseline branch lacked enforcement (consumers can ignore the marker).
  - #5 Iter-1 closures documented in prose, not operationalized.
- **Verdict:** REVISE.

### Iteration 3 — operationalized closures + 1:1 manifest invariant
- **Approach:** full-corpus determinism audit, frozen exclusion list, `test_manifest_consistency.py` enforcing PDF↔snapshot bijection, parametric over PDFs (no skips), 5-exemplar slicing self-test, programmatic UNUSABLE marker.
- **Codex findings (7):**
  - #1 **Manifest reality drift:** repo has 30 PDFs (not 27), 3 with malformed/truncated names (`.p` suffix, extensionless). Plan anchored on 27 throughout.
  - #2 `test_snapshot_count_nonzero >= 27` is a floor, not an equality assertion.
  - #3 **Default-CI assumption broken:** `validation_set/pdfs/` is GITIGNORED per `validation_set/README.md:33` (`gitignored — symlink or copy your 30 real PDFs here`). Existing `pyproject.toml` excludes `validation` marker by default. The plan moved real-extraction tests into default CI without addressing how CI/forks/fresh-clones obtain PDFs.
  - #4 **API mismatch:** `analyze_pdf(pdf_path, profile_name="army", ...)` per `analyzer.py:24`; plan's sample code calls `analyze_pdf(..., profile='army')`. Code wouldn't run.
  - #5 UNUSABLE-marker enforcement missing — no shared loader-guard, no test proving downstream units fail closed.
  - #6 5-row self-test inadequate for 866-row TSV; matching-key ambiguity policy missing (duplicate terms in doc, normalization, source-type).
  - #7 Determinism policy permits ratcheting exclusions to force green; no allowed-nondeterminism field-level policy up front.
- **Verdict:** ESCALATE.

## 3. Persistent failures

### Failure A: Plan rigor against repo reality

The most damning iter-3 findings (#1, #3, #4) are facts that should have been verified at planning time:
- 30 PDFs (not 27) — `ls validation_set/pdfs/ | wc -l` confirms.
- PDFs gitignored — first line of `validation_set/README.md` `## File layout` confirms.
- `analyze_pdf` parameter name — direct grep on `analyzer.py` confirms.

I cited candidate-output count (27) as evidence for a manifest of 27 PDFs without independently verifying the PDF directory. I assumed default-CI portability without reading `validation_set/README.md`. I wrote sample code for `analyze_pdf` from memory rather than from the actual signature. CLAUDE.md explicitly mandates this verification: *"Verify assumptions during planning, not execution."* I didn't.

### Failure B: The PDF portability problem is structural, not tactical

`validation_set/pdfs/` is gitignored by design — these are real Army Pubs PDFs that the repo can't redistribute. The existing test infrastructure (`tests/test_validation_set.py`) is correctly marked `@pytest.mark.validation` and skipped by default. Any plan that puts real-extraction tests into default CI is incompatible with that constraint.

This isn't fixable by tightening regex or adding tests. It's an architectural decision about Unit 1's role:
- **Default CI** can run unit-style tests against a small committed fixture (1-2 vendored PDFs, or pre-computed JSON inputs).
- **Real-extraction snapshot** must be opt-in (`@pytest.mark.validation` or similar) AND require local PDFs.
- **CI integration** for real extraction would need either GitHub Actions secret PDFs or a separate scheduled job with a PDF-bearing runner.

The plan repeatedly tried to put the snapshot oracle in default CI; iter-3 finally exposed why that can't work in this repo.

### Failure C: Findings shifted dimensions each iteration

Iter-1: data source wrong (auto-classifier vs hand-vetted).
Iter-2: operationalization gaps (manifest, determinism, fallback, invalid-baseline, closures).
Iter-3: real repo state (PDF count, portability, API name, malformed names).

Each iteration uncovered a NEW dimension because earlier iterations didn't audit the next layer. This is the wrong-boundary pattern from `~/.claude/projects/-Users-mw/memory/feedback_split_on_wrong_boundary_pattern.md` — repeated boundary-discovery rather than convergence. Per `feedback_review_iter_cap_convergence_judgment.md`, this does NOT qualify for operator-judgment APPROVED at the iter-3 cap.

## 4. Final Codex Adversarial Review

```
### Codex Adversarial Review (Iteration 3)
- **Status:** 0 SUCCESS
- **Findings:** 7 material
  #1: Manifest reality — 30 PDFs not 27; 3 malformed names
  #2: count >= 27 is a floor, not equality
  #3: Default-CI assumption breaks against gitignored PDFs and validation-marker convention
  #4: API mismatch — analyze_pdf takes profile_name not profile
  #5: UNUSABLE-marker enforcement guard missing
  #6: 5-row self-test inadequate for 866-row TSV; ambiguity policy missing
  #7: Determinism policy permits silent ratcheting of exclusions
- **Verdict impact:** Findings trajectory 5 → 5 → 7. Surface widening.
  Per feedback_review_iter_cap_convergence_judgment.md, does not qualify
  for operator-judgment APPROVED at iter-3 cap.
```

## 5. Blocking questions for human

### Q1: PDF portability — what's the corpus provisioning model for Unit 1's strict oracle?

Three structural options. The right answer depends on operational constraints I don't have visibility into:

- **A) Vendor 1-3 representative PDFs into the repo** (not gitignored). Default-CI snapshot test runs against vendored set; broader real-extraction is opt-in. Trade-off: licensing/redistribution concerns; small subset may not catch all extractor regressions.
- **B) Keep PDFs gitignored; snapshot oracle is opt-in via `@pytest.mark.validation`**. Default CI gets only manifest-consistency + slicing-contract-self-test. Real-extraction oracle runs locally OR in a separate scheduled CI job with PDF access. Trade-off: default CI doesn't catch extractor regressions.
- **C) Pre-extract PDFs to JSON committed inputs**, write snapshot test as JSON-in → JSON-out (no PDF needed). Default CI runs this. Trade-off: tests don't exercise pdfplumber/the wheel's PDF parsing path; only the post-parse logic.

### Q2: Is `labels-pending.tsv` actually meant to be a "vetted oracle"?

The TSV header has a `label` column that's empty in all 866 rows — suggesting it was DESIGNED as the human-confirmed-label slot, with `auto_guess` as the classifier's prediction. Was the user's "100 vetted from a couple of regs" referring to:
- batch1.yaml's spot-check (62 entries; index drift makes them unreliable today)?
- A separate hand-review process that intended to populate `label` but hasn't run?
- Something else (different file, different format)?

This determines whether Unit 1 should be:
- **D) Build infrastructure to populate `label` column from a hand-review session** (~3-5 hr Codex Z2 fix)
- **E) Use existing artifacts as-is, document UNUSABLE** (current plan iter-3 design)
- **F) Reconcile batch1.yaml indices to current candidate-output by content match** (~1-2 hr — may yield ~5 strict assertions)

### Q3: Should Unit 1 ship at all in this form?

Given iter-3 findings, an alternative is to **fold Unit 1 into Unit 4** (hand-vetting). Unit 4 already has scope to hand-vet labels for new docs; expanding it to also reconcile batch1.yaml + populate labels-pending.tsv's `label` column would produce a real oracle in one cohesive cycle, instead of two units fighting over the same "what is ground truth?" question.

## 6. Recommended next approach

**Option: Fold Unit 1 → Unit 4, with revised scope.** Specifically:

1. **Skip Unit 1 as currently designed.** No oracle infrastructure built on top of unverified labels.
2. **Expand Unit 4 to:**
   - Hand-vet ~50 entries across the 4 Section-I-heavy docs (already in scope)
   - Reconcile batch1.yaml's 5 hand-flips against current candidate-output (find the entries by content, capture as concrete `(term, def[:80])` pairs)
   - Populate `label` column in `labels-pending.tsv` for at least 100 entries (resolves the user's stated "100 vetted" expectation)
3. **Build a SMALLER snapshot test** — opt-in via `@pytest.mark.validation`, exercises 2-3 vendored representative PDFs (not all 30). Default CI runs manifest-consistency + slicing-self-test only.
4. **Defer the auto-classifier baseline measurement entirely** — it's informational and the planning-time numbers (468/698, 9/168) confirm provenance drift; it would emit UNUSABLE on day one. Not worth shipping.

This shrinks Unit 4 + skipped-Unit-1 to a ~3-4 hr cycle producing actual ground truth, instead of two units arguing about whether labels-pending.tsv counts as ground truth.

**Why I recommend this:** every iteration of Unit 1's plan-review hit a different limitation of the existing artifacts. The honest read is that the artifacts aren't ready to be an oracle — they're hand-spot-check data with provenance drift. Building scaffolding around them produces UNUSABLE-marked baselines and complicated test machinery for no measurable quality signal. Investing the same hours in actually completing the hand-vetting (which is Unit 4's mission anyway) produces real data.

## 7. Suggested rule for `~/.claude/CLAUDE.md`

The recurring planning-rigor failure (Failure A) was: I cited derived counts (e.g., "27 candidate-output JSONs") as evidence for upstream truth (e.g., "27 PDFs in manifest") without independent audit. CLAUDE.md already has *"Verify assumptions during planning, not execution"* but that didn't fire here because the failure mode was specific.

Suggested addition under "Planning Standards" or "Before You Act":

> **Verify the source-of-truth artifact, not its derivative.** When a plan asserts a count, a path, or a signature, verify against the canonical source (the PDF directory, the README spec, the function definition) — not against a downstream artifact (the candidate-output count, the file with the same name, a code sample from memory). A grep on the actual file is the verification; "looks consistent with adjacent artifacts" is not. Plans that skip this step will surface the discrepancy in iter-2 or iter-3 of plan review, after the structural design has been built around the wrong number.

Operator decides whether to add.

---

**Plan file path:** `docs/plans/2026-04-26-labels-pending-oracle.md` (iter-3 plan, retained for reference).

**Recommended next action:** discard Unit 1 as currently designed; expand Unit 4 per §6.

<promise>PLAN_ESCALATED</promise>
