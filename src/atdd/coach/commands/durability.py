"""Durable JSONL writers for coach state — `decisions.jsonl` and `judgments.jsonl`.

Spec references:
- §3.2 (runtime folder layout)
- §4.5 (decision durability — every transition appended *before* the action runs)
- §6.9 (`atdd judge` and `judgments.jsonl` — six call sites, inputs hashed by default)
- §C0 (`coach-decision.schema.json`, `coach-judgment.schema.json`)
- `runtime-layout.md` ("Append-only files never seek-and-truncate")

Public surface:
- ``DecisionWriter`` — append-only writer for `coach/decisions.jsonl`.
- ``JudgmentWriter`` — append-only writer for `coach/judgments.jsonl`,
  routes full inputs to a separate cache directory.
- ``transactional_decision`` — context manager enforcing the
  decision-precedes-action invariant and idempotent replay.
- ``hash_inputs`` — content-stable, order-independent hash for judgment inputs.
- ``SchemaValidationError`` — raised at write time when a record fails schema.

Design notes:
- Append-only is implemented via ``os.open`` with ``O_APPEND | O_CREAT |
  O_WRONLY``; each record is written as a single ``os.write`` call (one
  JSON line, terminating ``\n``). On POSIX this is atomic for writes
  ≤ ``PIPE_BUF`` (≥ 4096 on Linux/macOS), which covers normal coach records.
- ``fsync`` is called after each record to make the durable log resilient
  to crash; this is the load-bearing property for #J6 resume.
- Schema validation runs *before* any bytes hit the file. Invalid records
  raise ``SchemaValidationError`` naming the offending field and never
  open the file for write.
- Idempotency is implemented via a forward scan of the log for the
  ``decision_id``. For J3's expected log sizes (a few thousand records
  per coach run) this is acceptable; #J6 may layer a faster index.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterator, Optional

from jsonschema import Draft202012Validator

import atdd

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
SCHEMAS_DIR = ATDD_PKG_DIR / "coach" / "schemas"


class DurabilityError(Exception):
    """Base class for durability-writer errors."""


class SchemaValidationError(DurabilityError):
    """A record failed schema validation. The message names the offending field."""


def _load_validator(schema_filename: str) -> Draft202012Validator:
    schema_path = SCHEMAS_DIR / schema_filename
    schema = json.loads(schema_path.read_text())
    return Draft202012Validator(schema)


def _format_error(errors: list, schema_id: str) -> str:
    parts: list[str] = []
    for err in errors:
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        if err.validator == "required":
            missing = err.message.split("'")[1] if "'" in err.message else err.message
            parts.append(f"missing required field {missing!r}")
        else:
            parts.append(f"{path}: {err.message}")
    return f"{schema_id} validation failed: {'; '.join(parts)}"


def _append_jsonl(path: Path, record: dict) -> None:
    """Append one JSON line to ``path`` with O_APPEND + fsync semantics."""
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
    data = line.encode("utf-8")
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def hash_inputs(inputs: Any) -> str:
    """Order-independent SHA-256 hash of judgment inputs.

    Returns a string of the form ``sha256:<hex>``. Two payloads with the
    same content but different key orderings produce the same hash.
    """
    canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class DecisionWriter:
    """Append-only writer for ``<runtime_dir>/coach/decisions.jsonl``.

    Schema-validates every record against ``coach-decision.schema.json``
    before writing.
    """

    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = Path(runtime_dir)
        self.path = self.runtime_dir / "coach" / "decisions.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._validator = _load_validator("coach-decision.schema.json")

    def append(self, record: dict) -> None:
        errors = sorted(self._validator.iter_errors(record), key=lambda e: list(e.absolute_path))
        if errors:
            raise SchemaValidationError(_format_error(errors, "coach-decision"))
        _append_jsonl(self.path, record)

    def has_decision(self, decision_id: str) -> bool:
        if not self.path.exists():
            return False
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("decision_id") == decision_id:
                    return True
        return False


class JudgmentWriter:
    """Append-only writer for ``<runtime_dir>/coach/judgments.jsonl``.

    Schema-validates every record against ``coach-judgment.schema.json``
    before writing. Optionally persists full inputs to a sibling cache
    directory keyed by ``inputs_hash``; the durable log itself only
    carries the hash, per spec §6.9.
    """

    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = Path(runtime_dir)
        self.path = self.runtime_dir / "coach" / "judgments.jsonl"
        self.cache_dir = self.runtime_dir / "coach" / "judgment-inputs"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._validator = _load_validator("coach-judgment.schema.json")

    def append(self, record: dict, *, full_inputs: Optional[Any] = None) -> None:
        errors = sorted(self._validator.iter_errors(record), key=lambda e: list(e.absolute_path))
        if errors:
            raise SchemaValidationError(_format_error(errors, "coach-judgment"))
        if full_inputs is not None:
            self._cache_full_inputs(record["inputs_hash"], full_inputs)
        _append_jsonl(self.path, record)

    def _cache_full_inputs(self, inputs_hash: str, full_inputs: Any) -> None:
        safe_name = inputs_hash.replace(":", "_").replace("/", "_") + ".json"
        target = self.cache_dir / safe_name
        tmp = target.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(full_inputs, separators=(",", ":"), ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, target)


@contextlib.contextmanager
def transactional_decision(
    writer: DecisionWriter, record: dict
) -> Iterator[bool]:
    """Decision-precedes-action context manager.

    On entry: if ``record["decision_id"]`` already exists in the durable
    log, yield ``False`` so the caller skips the action (idempotent
    replay). Otherwise, append the decision *before* yielding ``True``;
    if the body raises, the decision is still durably recorded (#J6
    resume contract).
    """
    if writer.has_decision(record["decision_id"]):
        yield False
        return
    writer.append(record)
    yield True
