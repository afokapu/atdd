"""CLI controller for the coach runtime — `atdd coach <start|wait|next|stop|daemons>`.

Thin shell: parse the verb + flags, build the use case from the repo via the
composition root, and run it. All wiring lives in composition.py; the
wait/cursor decision lives in the pure domain core.

Skeleton: bodies land in GREEN.
"""
from __future__ import annotations

import argparse
from typing import List, Optional

VERBS = ("start", "wait", "next", "stop", "daemons")


def _build_parser() -> argparse.ArgumentParser:
    raise NotImplementedError("GREEN")


def run(argv: Optional[List[str]] = None) -> int:
    raise NotImplementedError("GREEN")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
