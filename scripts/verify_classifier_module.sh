#!/bin/bash
# Codex iter-3 #1 + iter-4 #3 fix: verify the extracted classifier module is
# importable from a fresh editable install AND the script entrypoint still
# runs. Two smaller checks instead of one brittle script-entrypoint probe.
#
# Runs in §6 step 2 of the PR4-classifier plan (right after extraction,
# before Option B fixes land).
#
# Uses python3 (not `python`) which is what's on PATH. No Makefile reference.
set -euo pipefail

VENV_DIR="${VENV_DIR:-/tmp/fr-classifier-verify-venv}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cleanup() {
  rm -rf "$VENV_DIR"
}
trap cleanup EXIT

echo "=== Creating fresh venv at $VENV_DIR ==="
python3 -m venv "$VENV_DIR"

echo "=== Installing repo with [dev] extras ==="
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e "$REPO_ROOT[dev]"

echo "=== GATE 1: Import-only smoke (module contract) ==="
"$VENV_DIR/bin/python" -c "
from fedresearch_dictionary_extractor.labels_classifier import classify
# Basic sanity: a clear good entry classifies as 'g'
assert classify('Active duty', 'Full-time military service of the United States.') == 'g'
# A clear noise term classifies as 'b'
assert classify('UNCLASSIFIED', 'PIN 123456-000') == 'b'
print('IMPORT CONTRACT: PASS')
"

echo "=== GATE 2: Script-entrypoint smoke (realistic invocation) ==="
cd "$REPO_ROOT"
"$VENV_DIR/bin/python" scripts/build_labels_yaml.py
test -f validation_set/labels.yaml
echo "SCRIPT ENTRYPOINT: PASS"

echo ""
echo "=== ALL GATES PASSED ==="
