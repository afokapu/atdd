"""Shared single-writer JSONL append (wagon-internal commons).

Used by every sink/ledger in the wagon so the "mkdir + append one JSON line"
logic lives in exactly one place instead of being copied per integration
adapter.
"""
from __future__ import annotations

import json
from pathlib import Path


def append_jsonl(path: Path, record: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
