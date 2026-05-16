"""Tests for ``--deterministic`` CLI flag and ``deterministic`` analyze_pdf
parameter (PR-A v0.3.0 fix #5).

Background: the extractor's JSON output embeds ``extraction_timestamp =
datetime.now(UTC)``, so two runs against the same input PDF produce
byte-different output. This blocks the FedResearch backend from using
the JSON as a cache key (the v0.2.0 corpus regen script in
docs/plans/2026-04-26-v0.2.0-release.md §3.2 manually strips the
timestamp before comparison — a workaround, not a fix).

Fix #5 adds ``--deterministic`` (CLI) and the equivalent
``deterministic=True`` kwarg to ``analyze_pdf``. When set, all
wall-clock-derived fields are omitted from the output payload, making
two runs against the same input byte-identical. Schema field
``extraction_timestamp`` is moved out of ``required`` (additive,
back-compat for downstream consumers that already treat it as optional).

Default behavior (no flag) is unchanged from v0.2.0.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import fitz
import pytest

from fedresearch_dictionary_extractor.core.analyzer import analyze_pdf


# ----------------------------------------------------------------------
# Synthetic PDF fixture — tiny, deterministic, fast
# ----------------------------------------------------------------------


@pytest.fixture
def tiny_pdf(tmp_path: Path) -> Path:
    """A 1-page PDF with a single line of body text. Sufficient to exercise
    analyze_pdf end-to-end without hauling in a multi-MB validation PDF."""
    path = tmp_path / "tiny.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Sample document body text.", fontsize=10)
    doc.save(str(path))
    doc.close()
    return path


# ----------------------------------------------------------------------
# analyze_pdf-level tests
# ----------------------------------------------------------------------


def test_analyze_pdf_deterministic_omits_timestamp(tiny_pdf: Path) -> None:
    """deterministic=True suppresses extraction_timestamp."""
    out = analyze_pdf(tiny_pdf, deterministic=True)
    assert "extraction_timestamp" not in out, (
        f"deterministic=True must not emit extraction_timestamp; "
        f"keys: {sorted(out.keys())}"
    )


def test_analyze_pdf_default_keeps_timestamp(tiny_pdf: Path) -> None:
    """Back-compat: omitting deterministic keeps the timestamp (v0.2.0 shape)."""
    out = analyze_pdf(tiny_pdf)
    assert "extraction_timestamp" in out, (
        f"Default behavior must emit extraction_timestamp; "
        f"keys: {sorted(out.keys())}"
    )


def test_analyze_pdf_deterministic_two_runs_equal(tiny_pdf: Path) -> None:
    """Two consecutive deterministic runs against the same PDF produce
    structurally identical output (key-by-key equality)."""
    a = analyze_pdf(tiny_pdf, deterministic=True)
    b = analyze_pdf(tiny_pdf, deterministic=True)
    assert a == b, "Two deterministic runs must produce identical payloads"


# ----------------------------------------------------------------------
# CLI-level test — verify the --deterministic flag plumbs through
# ----------------------------------------------------------------------


def test_cli_deterministic_flag_byte_identical(tiny_pdf: Path, tmp_path: Path) -> None:
    """`extract-definitions --deterministic` produces byte-identical output
    across two runs against the same input."""
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    cmd_a = [
        sys.executable,
        "-m",
        "fedresearch_dictionary_extractor.cli",
        "--deterministic",
        "--input",
        str(tiny_pdf),
        "--output",
        str(out_a),
    ]
    cmd_b = list(cmd_a)
    cmd_b[-1] = str(out_b)
    rc_a = subprocess.call(cmd_a)
    rc_b = subprocess.call(cmd_b)
    assert rc_a == 0 and rc_b == 0, "CLI invocations must succeed"
    bytes_a = out_a.read_bytes()
    bytes_b = out_b.read_bytes()
    assert bytes_a == bytes_b, (
        f"Two --deterministic runs must produce byte-identical JSON; "
        f"diff at first byte: {next((i for i, (x, y) in enumerate(zip(bytes_a, bytes_b)) if x != y), -1)}"
    )


def test_cli_default_run_emits_timestamp_field(tiny_pdf: Path, tmp_path: Path) -> None:
    """Negative regression guard: default CLI run still emits extraction_timestamp."""
    out_path = tmp_path / "default.json"
    rc = subprocess.call(
        [
            sys.executable,
            "-m",
            "fedresearch_dictionary_extractor.cli",
            "--input",
            str(tiny_pdf),
            "--output",
            str(out_path),
        ]
    )
    assert rc == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert "extraction_timestamp" in payload, "Default CLI run must keep extraction_timestamp"
