"""
extract-definitions CLI.

Single-doc mode (called by NestJS subprocess):
    extract-definitions --input <pdf> --output <json>
                        [--profile army] [--gcs-key <key>] [--doc-id <id>]

Batch mode (called from local backfill):
    extract-definitions --input-dir <dir> --output-dir <dir>
                        [--workers N] [--manifest <manifest.json>]
                        [--profile army]
"""
from __future__ import annotations

import argparse
import json
import logging
import multiprocessing as mp
import sys
from pathlib import Path

from . import __version__
from .core.analyzer import analyze_pdf
from .json_output import write_json

LOG = logging.getLogger("extract-definitions")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="extract-definitions",
        description="Extract glossary + inline definitions from Army regulation PDFs.",
    )
    p.add_argument("--version", action="version", version=f"extract-definitions {__version__}")

    # Single-doc args
    p.add_argument("--input", type=Path, help="Single PDF to extract.")
    p.add_argument("--output", type=Path, help="JSON output path (single-doc mode).")
    p.add_argument("--gcs-key", default=None, help="GCS object key, written into output metadata.")
    p.add_argument("--doc-id", default=None, help="FedResearch document id, written into output metadata.")

    # Batch args
    p.add_argument("--input-dir", type=Path, help="Directory of PDFs to extract (batch mode).")
    p.add_argument("--output-dir", type=Path, help="Directory for JSON outputs (batch mode).")
    p.add_argument("--workers", type=int, default=4, help="Worker processes for batch mode.")
    p.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="JSON file mapping {local_path: {gcs_key, doc_id}} for batch mode.",
    )

    p.add_argument("--profile", default="army", help="Profile name (default: army).")
    p.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip JSON-schema validation (NOT RECOMMENDED; use only for triage).",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    is_single = bool(args.input)
    is_batch = bool(args.input_dir)
    if is_single == is_batch:
        LOG.error("Pass exactly ONE of: --input (single) or --input-dir (batch).")
        return 2

    if is_single:
        if not args.output:
            LOG.error("--input requires --output.")
            return 2
        return _run_single(args)
    return _run_batch(args)


def _run_single(args: argparse.Namespace) -> int:
    if not args.input.exists():
        LOG.error("Input PDF does not exist: %s", args.input)
        return 1
    LOG.info("Extracting %s …", args.input)
    payload = analyze_pdf(
        args.input,
        profile_name=args.profile,
        gcs_key=args.gcs_key,
        doc_id=args.doc_id,
    )
    write_json(payload, args.output, validate_first=not args.no_validate)
    LOG.info(
        "Wrote %s — %d entries (glossary=%d, inline=%d, after_dedup=%d)",
        args.output,
        len(payload["entries"]),
        payload["metadata"]["entries_glossary"],
        payload["metadata"]["entries_inline"],
        payload["metadata"]["entries_after_dedup"],
    )
    return 0


def _run_batch(args: argparse.Namespace) -> int:
    if not args.input_dir.exists():
        LOG.error("Input dir does not exist: %s", args.input_dir)
        return 1
    if not args.output_dir:
        LOG.error("--input-dir requires --output-dir.")
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, dict] = {}
    if args.manifest:
        if not args.manifest.exists():
            LOG.error("Manifest file does not exist: %s", args.manifest)
            return 1
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))

    pdfs = sorted(args.input_dir.rglob("*.pdf"))
    LOG.info("Found %d PDFs in %s.", len(pdfs), args.input_dir)
    if not pdfs:
        return 0

    jobs = []
    for pdf in pdfs:
        # Manifest keys may be relative-to-input-dir or absolute. Try both.
        rel = str(pdf.relative_to(args.input_dir))
        meta = manifest.get(str(pdf)) or manifest.get(rel) or {}
        out_path = args.output_dir / (pdf.stem + ".json")
        jobs.append((str(pdf), str(out_path), args.profile, meta.get("gcs_key"), meta.get("doc_id"), args.no_validate))

    no_definitions: list[str] = []
    failures: list[tuple[str, str]] = []

    with mp.get_context("spawn").Pool(args.workers) as pool:
        for source_pdf, status, message in pool.imap_unordered(_worker, jobs, chunksize=1):
            if status == "ok":
                LOG.info("✓ %s — %s", source_pdf, message)
            elif status == "no-defs":
                LOG.info("∅ %s — no definitions", source_pdf)
                no_definitions.append(source_pdf)
            else:
                LOG.error("✗ %s — %s", source_pdf, message)
                failures.append((source_pdf, message))

    # Write summary files
    if no_definitions:
        (args.output_dir / "NO_DEFINITIONS.txt").write_text("\n".join(no_definitions) + "\n")
    if failures:
        (args.output_dir / "FAILURES.txt").write_text(
            "\n".join(f"{p}\t{e}" for p, e in failures) + "\n"
        )

    LOG.info(
        "Done. %d ok, %d no-defs, %d failures.",
        len(pdfs) - len(no_definitions) - len(failures),
        len(no_definitions),
        len(failures),
    )
    return 0 if not failures else 1


def _worker(args: tuple) -> tuple[str, str, str]:
    """Pickleable worker: returns (source_pdf, status, message)."""
    source_pdf, output_path, profile_name, gcs_key, doc_id, no_validate = args
    try:
        payload = analyze_pdf(source_pdf, profile_name=profile_name, gcs_key=gcs_key, doc_id=doc_id)
        write_json(payload, output_path, validate_first=not no_validate)
        n = payload["metadata"]["entries_after_dedup"]
        if n == 0:
            return (source_pdf, "no-defs", "")
        return (source_pdf, "ok", f"{n} entries")
    except Exception as exc:  # noqa: BLE001 — surface unexpected failures
        return (source_pdf, "fail", f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
