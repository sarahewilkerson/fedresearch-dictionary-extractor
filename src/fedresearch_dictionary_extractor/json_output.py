"""
Schema-validated JSON emitter. Wraps the analyzer payload and validates
it against schema/definition-output-v1.json before write.
"""
from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

_SCHEMA_CACHE: dict[str, Any] | None = None


def _load_schema() -> dict[str, Any]:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        schema_text = (
            files("fedresearch_dictionary_extractor.schema")
            .joinpath("definition-output-v1.json")
            .read_text(encoding="utf-8")
        )
        _SCHEMA_CACHE = json.loads(schema_text)
    return _SCHEMA_CACHE


def validate(payload: dict[str, Any]) -> None:
    """
    Raise jsonschema.ValidationError if payload doesn't match schema v1.
    Imported lazily so the package's runtime dependencies stay minimal —
    jsonschema is only needed at validate time.
    """
    import jsonschema

    schema = _load_schema()
    jsonschema.validate(instance=payload, schema=schema)


def write_json(payload: dict[str, Any], output_path: str | Path, *, validate_first: bool = True) -> Path:
    """Validate (optionally) and write payload to output_path. Returns the path."""
    output_path = Path(output_path)
    if validate_first:
        validate(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path
