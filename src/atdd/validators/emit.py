"""Validator emission (docs/coach-decomposition.md §4.11).

Every validator emits :class:`ValidatorReport` rows via :func:`emit_reports`,
which appends them to the active run's persistence store so
``materialize_evidence()`` can read them back into ``Evidence.validator_reports``.

Run resolution is environment-driven so a validator stays oblivious to *where*
it runs:

1. ``ATDD_VALIDATOR_REPORTS_PATH`` — explicit sink file (set by
   ``atdd validate --collect-reports``).
2. ``ATDD_RUN_DIR`` — a run directory; reports go to ``<dir>/validator-reports.jsonl``.
3. ``ATDD_RUN_ID`` (+ optional ``ATDD_REPO_ROOT``) — reports go to
   ``<repo_root>/.atdd/runtime/runs/<run_id>/validator-reports.jsonl`` (§5.1).

When no run context is set (a plain ``pytest`` / ``atdd validate`` run),
:func:`emit_reports` is a safe no-op so ordinary runs never litter the tree.
Emission is always best-effort: an I/O error never propagates into the gate.
"""
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Iterable

from atdd.coach.core.types import ValidatorReport

ENV_REPORTS_PATH = "ATDD_VALIDATOR_REPORTS_PATH"
ENV_RUN_DIR = "ATDD_RUN_DIR"
ENV_RUN_ID = "ATDD_RUN_ID"
ENV_REPO_ROOT = "ATDD_REPO_ROOT"

REPORTS_FILENAME = "validator-reports.jsonl"


def resolve_reports_path() -> Path | None:
    """Return the active run's reports file, or ``None`` when no run context.

    Reads environment only; does not create anything.
    """
    explicit = os.environ.get(ENV_REPORTS_PATH)
    if explicit:
        return Path(explicit)

    run_dir = os.environ.get(ENV_RUN_DIR)
    if run_dir:
        return Path(run_dir) / REPORTS_FILENAME

    run_id = os.environ.get(ENV_RUN_ID)
    if run_id:
        repo_root = Path(os.environ.get(ENV_REPO_ROOT, ".")).resolve()
        return repo_root / ".atdd" / "runtime" / "runs" / run_id / REPORTS_FILENAME

    return None


def emit_reports(reports: Iterable[ValidatorReport]) -> None:
    """Append ``reports`` to the active run's ``validator-reports.jsonl``.

    No-op when there are no reports or no run context is configured. Best-effort:
    filesystem errors are swallowed so emission never breaks a validator gate.
    """
    rows = list(reports)
    if not rows:
        return

    path = resolve_reports_path()
    if path is None:
        return

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for report in rows:
                handle.write(json.dumps(dataclasses.asdict(report), sort_keys=True))
                handle.write("\n")
    except OSError:
        return


__all__ = [
    "emit_reports",
    "resolve_reports_path",
    "ENV_REPORTS_PATH",
    "ENV_RUN_DIR",
    "ENV_RUN_ID",
    "ENV_REPO_ROOT",
    "REPORTS_FILENAME",
]
