"""Shared single-writer JSONL append (wagon-internal commons).

Used by every sink/ledger in the wagon so the "mkdir + append one JSON line"
logic lives in exactly one place instead of being copied per integration
adapter.

The append is crash-safe (#1084 B1): the new line is staged in a sibling temp
file that is ``fsync``-ed and then ``os.replace``-d over the ledger atomically.
A crash before the swap leaves the original ledger untouched (all-or-nothing —
never a truncated half-line), and the ``fsync`` forces a committed record to
stable storage so it is not lost. Mirrors the ``FileCursorStore`` durability
pattern (``jsonl_escalation_reader``).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

_LOG = logging.getLogger("atdd.mediate_worker_decisions.jsonl_writer")


def append_jsonl(path: Path, record: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
    existing = target.read_bytes() if target.exists() else b""

    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=target.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(existing)
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())  # committed bytes forced to disk (no loss)
        os.replace(tmp_name, target)  # atomic swap — never a half-written ledger
    except BaseException:
        # Commit failed: discard the staged temp file and leave the live ledger
        # exactly as it was (all-or-nothing), then surface the failure.
        try:
            os.unlink(tmp_name)
        except OSError:
            _LOG.warning(
                "could not remove staged temp ledger file %s after a failed "
                "append commit",
                tmp_name,
                exc_info=True,
            )
        raise
