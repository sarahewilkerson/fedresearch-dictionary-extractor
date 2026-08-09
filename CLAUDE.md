# FedResearch Dictionary Extractor — Project Config

Thin per-repo config consumed by `/develop` and the review gates. Pipeline scope and program state
live in the global `~/.claude/CLAUDE.md` and FedResearch memory (dictionary pipeline audit).

## Project Config
- Main branch: `main`
- Test command: `pytest -q` (as CI runs it)
- Lint command: `ruff check src tests` (as CI runs it — not `ruff check .`)
- No Makefile; there are no `make` targets in this repo.

## Test-suite shape

`pyproject.toml` sets `testpaths = ["tests"]`, `pythonpath = ["src"]`, and
`addopts = "-ra --strict-markers -m 'not validation'"`.

**The default run silently excludes the `validation` marker.** Those tests need a real-PDF
validation set (`validation_set/labels.yaml` + `validation_set/pdfs/`) and are opt-in via
`pytest -m validation`. A green default run is therefore not evidence that extraction accuracy
holds — it is evidence that everything *except* the accuracy suite passes. `--strict-markers`
means a typo'd marker is an error, not a silent skip.

## CI

Single workflow `.github/workflows/ci.yml`: lint + pytest across a Python matrix, then a
build job producing wheel/sdist and a SHA-256 that the Dockerfile pinning contract consumes.
Runners are self-hosted (see the global config — no GitHub-hosted runners in this org).

**Interpreters come from `uv`, not `actions/setup-python`.** The runner host is Debian 13
(trixie), for which `actions/python-versions` publishes no x64 builds, and trixie carries only
3.13 — so setup-python cannot provision 3.11 or 3.12 and there is no apt path. Do not "simplify"
this back to setup-python, and do not narrow the matrix to the system 3.13: that would silently
drop the support this package declares.
