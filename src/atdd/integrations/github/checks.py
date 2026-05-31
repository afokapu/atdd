"""GitHub check-run adapter (docs/coach-decomposition.md §4.10).

Reads check runs for a commit and re-triggers workflow runs. Returns plain
:class:`CheckRunData`; Child 7 maps these onto Coach-core ``CheckRun``.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from atdd.integrations.github import _gh
from atdd.integrations.github.types import CheckRunData

_log = logging.getLogger(__name__)


def read_check_runs(
    sha: str, *, repo_root: Optional[Path] = None
) -> tuple[CheckRunData, ...]:
    """Return the check runs reported against commit *sha*."""
    cfg = _gh.resolve_project_config(repo_root)
    out = _gh.run_gh(
        ["api", f"repos/{cfg.repo}/commits/{sha}/check-runs", "--paginate"]
    )
    data = json.loads(out) if out else {}
    runs: list[CheckRunData] = []
    for run in data.get("check_runs", []):
        # A run still in progress has conclusion == null → report PENDING.
        conclusion = run.get("conclusion") or "PENDING"
        workflow_id = (run.get("check_suite") or {}).get("id")
        runs.append(
            CheckRunData(
                name=run.get("name", ""),
                conclusion=str(conclusion).upper(),
                workflow_id=workflow_id,
            )
        )
    return tuple(runs)


def trigger_rerun(run_id: int) -> None:
    """Re-run the failed jobs of workflow run *run_id*."""
    _gh.run_gh(["run", "rerun", str(run_id), "--failed"])
    _log.info("Triggered workflow rerun", extra={"run_id": run_id})


__all__ = ["read_check_runs", "trigger_rerun"]
