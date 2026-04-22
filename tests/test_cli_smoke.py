"""
Smoke test for the CLI: ensures the entry point exists, --version works,
and bad arg combos exit non-zero.
"""
import subprocess
import sys


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "fedresearch_dictionary_extractor.cli", *args],
        capture_output=True,
        text=True,
    )


def test_version() -> None:
    r = _run("--version")
    assert r.returncode == 0
    assert "extract-definitions" in r.stdout


def test_no_mode_is_error() -> None:
    r = _run()
    assert r.returncode == 2


def test_input_without_output_is_error(tmp_path) -> None:
    fake_pdf = tmp_path / "x.pdf"
    fake_pdf.write_bytes(b"")
    r = _run("--input", str(fake_pdf))
    assert r.returncode == 2


def test_both_modes_specified_is_error(tmp_path) -> None:
    fake_pdf = tmp_path / "x.pdf"
    fake_pdf.write_bytes(b"")
    fake_dir = tmp_path / "in"
    fake_dir.mkdir()
    r = _run(
        "--input", str(fake_pdf),
        "--output", str(tmp_path / "out.json"),
        "--input-dir", str(fake_dir),
        "--output-dir", str(tmp_path / "outdir"),
    )
    assert r.returncode == 2
