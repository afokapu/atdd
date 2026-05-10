"""Pytest plugin: coach violation collector (issue #518).

Captures every ``Violation`` record that flows through the substrate's
``assert_disposition_satisfied`` helper during a coach-driven validator
dispatch and writes them to the SHA-keyed JSONL artifact.

Loaded by coach via argv injection (``-p
atdd.coach.plugins.violation_collector``) under
``PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`` per
``src/atdd/coach/schemas/validator-invocation.md``. NEVER auto-loaded via
``conftest.py`` or ``pytest_plugins`` — that would leak collection
behavior into unrelated test runs.

Output shape:
  ``<runtime_dir>/validations/<sha>/violations.jsonl`` — one
  ``validator-result.schema.json`` record per line.

Configuration (env-var only — coach passes verbatim per
validator-invocation.md §5):
  * ``ATDD_VALIDATION_SHA`` — commit SHA the dispatch is keyed by.
    Falls back to ``git rev-parse HEAD`` in the repo root.
  * ``ATDD_RUNTIME_DIR`` — runtime root (default
    ``<repo-root>/.atdd/runtime``).

Spec references: §6.4 step 4 (Violation collection), §7.5 (validator
output schema), validator-invocation.md, runtime-layout.md.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from atdd.coach.utils.disposition_gate import (
    get_active_pytest_session,
    set_active_pytest_session,
)
from atdd.coach.utils.repo import find_repo_root


# ---------------------------------------------------------------------------
# Pytest hooks
# ---------------------------------------------------------------------------


def pytest_sessionstart(session: pytest.Session) -> None:
    """Wire the coach session reference + initialize the observation list.

    After this hook runs, every call to
    ``assert_disposition_satisfied`` records each Violation it sees onto
    ``session._atdd["observed_violations"]`` via the substrate's existing
    active-session pattern.
    """
    namespace = getattr(session, "_atdd", None)
    if not isinstance(namespace, dict):
        namespace = {}
        try:
            setattr(session, "_atdd", namespace)
        except (AttributeError, TypeError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            # The session object cannot host our namespace (test harness
            # passed something exotic). Skip wiring; nothing to record.
            return
    namespace.setdefault("observed_violations", [])
    set_active_pytest_session(session)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Serialize captured Violations to ``violations.jsonl`` and detach."""
    if get_active_pytest_session() is session:
        set_active_pytest_session(None)

    namespace = getattr(session, "_atdd", None)
    observed: List[Dict[str, Any]] = []
    if isinstance(namespace, dict):
        candidate = namespace.get("observed_violations")
        if isinstance(candidate, list):
            observed = candidate

    out_path = _resolve_output_path(session)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Open append + create so a multi-shard pytest invocation can route into
    # the same file without truncating the predecessor's output. Coach owns
    # the cross-run lifecycle (a new SHA gets a fresh directory).
    with open(out_path, "a", encoding="utf-8") as fh:
        for entry in observed:
            record = _build_record(entry)
            if record is None:
                continue
            try:
                line = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
            except (TypeError, ValueError) as exc:
                # One bad record must not lose the rest. Log to stderr so the
                # coach run sees the failure; keep flushing the remainder.
                print(
                    f"[violation_collector] skipping non-serializable record "
                    f"for rule_id={record.get('rule_id')!r}: {exc}",
                    file=sys.stderr,
                )
                continue
            fh.write(line)
            fh.write("\n")


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _build_record(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Translate one observation into a validator-result.schema.json record.

    Returns None when the entry is malformed (missing the violation object);
    the plugin logs and continues so other records still flush.
    """
    violation = entry.get("violation")
    if violation is None:
        return None
    rule_id = getattr(violation, "rule_id", None)
    severity = getattr(violation, "severity", None)
    location = getattr(violation, "location", None)
    detail = getattr(violation, "detail", None)
    if rule_id is None or severity is None or location is None or detail is None:
        return None
    record: Dict[str, Any] = {
        "validator_id": entry.get("validator_id", ""),
        "rule_id": rule_id,
        "severity": severity,
        "disposition": entry.get("disposition", "strict"),
        "location": location,
        "detail": detail,
        "suppression_marker": entry.get("suppression_marker"),
    }
    fix_hint_ref = getattr(violation, "fix_hint_ref", None)
    if fix_hint_ref:
        record["fix_hint_ref"] = fix_hint_ref
    return record


def _resolve_output_path(session: pytest.Session) -> Path:
    """Compute ``<runtime_dir>/validations/<sha>/violations.jsonl``."""
    repo_root = _resolve_repo_root(session)
    runtime_dir_env = os.environ.get("ATDD_RUNTIME_DIR")
    if runtime_dir_env:
        runtime_dir = Path(runtime_dir_env)
    else:
        runtime_dir = repo_root / ".atdd" / "runtime"
    sha = _resolve_sha(repo_root)
    return runtime_dir / "validations" / sha / "violations.jsonl"


def _resolve_repo_root(session: pytest.Session) -> Path:
    """Best-effort repo root resolution that tolerates synthetic sessions."""
    rootpath = getattr(getattr(session, "config", None), "rootpath", None)
    if rootpath is not None:
        return Path(rootpath)
    try:
        return find_repo_root()
    except (RuntimeError, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        # No repo on disk (synthetic test session). Fall back to the cwd
        # which is what the substrate's other plugins use as last resort.
        return Path.cwd()


def _resolve_sha(repo_root: Path) -> str:
    """Resolve the dispatch SHA from env, then ``git rev-parse HEAD``."""
    env_sha = os.environ.get("ATDD_VALIDATION_SHA")
    if env_sha:
        return env_sha.strip()
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout.strip() or "unknown"
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        # No git, no env override, nothing to anchor on. Use a sentinel so
        # the plugin still produces an artifact coach can see (and the
        # subprocess test asserts on a synthetic SHA via ATDD_VALIDATION_SHA).
        print(
            f"[violation_collector] git rev-parse HEAD failed in {repo_root}: "
            f"{exc}; using SHA sentinel 'unknown'",
            file=sys.stderr,
        )
        return "unknown"


__all__ = [
    "pytest_sessionstart",
    "pytest_sessionfinish",
]
