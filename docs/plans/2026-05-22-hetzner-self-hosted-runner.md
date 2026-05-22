# Hetzner Self-Hosted Actions Runner — Dictionary Extractor

**Branch:** `feat/2026-05-22-hetzner-self-hosted-runner`
**Author:** Malcolm Wilkerson (claude-opus-4-7)
**Class:** lighter path (workflow-meta + ops; easily revertable; CI is the only consumer)

**Meta-plan (FR-family coexistence model):**
`sarahewilkerson/fedresearch/docs/plans/2026-05-22-hetzner-self-hosted-runners-fr-family.md`

This sibling plan covers the dictionary-extractor-specific portion.

## Context

`sarahewilkerson` is a User account (not Org), so GitHub Actions
self-hosted runners are scoped per repo. Today we're standardizing on
a per-repo runner pattern on the Hetzner box for all FR-family repos
(see meta-plan for the architecture). This repo is the second of two
new runners landing today.

Notes specific to this repo:
- This repo is **public**, so GH-hosted runners are free here — CI was
  not billing-blocked (recent CI runs at 2026-05-18 were green in 47s).
  Migration is for family-consistency, not necessity.
- Workload is light: one `ci.yml` workflow with two jobs (lint + tests).
- No Docker / browser / heavy deps; pnpm + Python only.

## Plan

### Runner provisioning

Already complete on the host:
- Service: `actions.runner.sarahewilkerson-fedresearch-dictionary-extractor.hetzner-fr-dict.service`
- Dir: `/home/fedresearch-admin/actions-runner-fr-dict/`
- Labels: `[self-hosted, linux, fedresearch-dict]`
- Status: active + online (verified before this commit lands).

Provisioning recipe was identical to the meta-plan, with `<repo>` =
`fedresearch-dictionary-extractor`, `<tag>` = `dict`, `<label>` =
`fedresearch-dict`.

### Workflow retargeting

Both `runs-on:` declarations in `.github/workflows/ci.yml` change from
`ubuntu-latest` to `[self-hosted, linux, fedresearch-dict]`.

No skip-list for this repo — only two jobs, both are lint/test, both
viable on Hetzner.

## Verification

1. Runner online — `gh api /repos/sarahewilkerson/fedresearch-dictionary-extractor/actions/runners`
   shows `hetzner-fr-dict` with `status: online`.
2. Push triggers CI; job picked up by the new runner. Wait for green.
3. Existing FR-main + FR-scraper runners unaffected.

## Rollback

Revert this commit. CI returns to GH-hosted runners and continues
running on free minutes.

## Hard 30%

Same considerations as the meta-plan:
- Disk pressure on Hetzner from a third `_work` dir (deferred monitoring).
- Host-level deps (libpango, black) — neither used by this repo's
  workflow, so not a concern here.
