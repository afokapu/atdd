"""Coach validator dispatcher (issue #518).

Subprocess wrapper that invokes ``python -m pytest`` against the validator
set selected for the current ``(phase, scope)`` with the violation
collector plugin attached. Per
``src/atdd/coach/schemas/validator-invocation.md`` (frozen at C0):

  * Plugin autoload is disabled (``PYTEST_DISABLE_PLUGIN_AUTOLOAD=1``).
  * Plugins are loaded via explicit ``-p`` flags only.
  * Env-var passthrough is whitelisted (PATH, HOME, PYTHONPATH,
    PYTEST_DISABLE_PLUGIN_AUTOLOAD, ATDD_VALIDATOR_TIMEOUT_*,
    ATDD_RUN_ID, CI, GITHUB_TOKEN [opt-in], LANG, LC_ALL).

The dispatcher is intentionally minimal: it builds the argv + env per the
invocation contract, runs the subprocess, and returns the exit code +
the path to the violation collector's JSONL output. Validator selection
(per-phase ∪ repo.* rules) is owned by issue #M3; suppression filtering
is owned by #M4; risk scoring is owned by #M5.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence


_ENV_PASSTHROUGH = (
    "PATH",
    "HOME",
    "PYTHONPATH",
    "ATDD_RUN_ID",
    "CI",
    "LANG",
    "LC_ALL",
)


@dataclass(frozen=True)
class DispatchResult:
    """Outcome of one validator dispatch.

    Attributes:
        exit_code: Pytest's exit code. ``0`` is clean; ``1..4`` is a test
            failure with structured records; ``5..6`` may be a subprocess
            crash (see validator-invocation.md §4.2). Coach distinguishes
            via ``violations_path`` non-emptiness.
        violations_path: Path to ``violations.jsonl`` for the dispatch's
            SHA. Always set; the file may not exist if the subprocess
            crashed before the plugin's ``pytest_sessionfinish`` ran.
        stdout: Captured stdout (subprocess pytest output).
        stderr: Captured stderr.
    """

    exit_code: int
    violations_path: Path
    stdout: str
    stderr: str


def dispatch_validators(
    *,
    sha: str,
    validator_paths: Sequence[Path],
    repo_root: Path,
    runtime_dir: Optional[Path] = None,
    timeout_seconds: Optional[int] = None,
    extra_env: Optional[Mapping[str, str]] = None,
) -> DispatchResult:
    """Invoke pytest with the violation_collector plugin against
    ``validator_paths`` and return the outcome.

    Args:
        sha: The commit SHA the dispatch is keyed by. Surfaces in
            ``<runtime_dir>/validations/<sha>/violations.jsonl`` and is
            forwarded to the plugin via ``ATDD_VALIDATION_SHA``.
        validator_paths: Test paths to run (one or more). Coach's
            per-phase selector (#M3) computes this set.
        repo_root: The agent's worktree root. Used as ``--rootdir`` so
            the subprocess is independent of the caller's cwd.
        runtime_dir: Override for the runtime root (default
            ``<repo_root>/.atdd/runtime``). Forwarded via
            ``ATDD_RUNTIME_DIR``.
        timeout_seconds: Per-phase timeout from
            validator-invocation.md §3. ``None`` lets pytest run to
            completion.
        extra_env: Optional additional env-var entries (e.g.
            ``ATDD_VALIDATOR_TIMEOUT_REFACTOR``); merged on top of the
            whitelisted passthrough set.
    """
    runtime = runtime_dir if runtime_dir is not None else repo_root / ".atdd" / "runtime"
    violations_path = runtime / "validations" / sha / "violations.jsonl"

    argv = _build_argv(repo_root=repo_root, validator_paths=validator_paths)
    env = _build_env(sha=sha, runtime_dir=runtime, extra_env=extra_env)

    proc = subprocess.run(
        argv,
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return DispatchResult(
        exit_code=proc.returncode,
        violations_path=violations_path,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def _build_argv(*, repo_root: Path, validator_paths: Iterable[Path]) -> list[str]:
    """Assemble the pytest argv per validator-invocation.md §1."""
    argv = [
        sys.executable,
        "-m",
        "pytest",
        "--tb=short",
        "-q",
        "--strict-markers",
        "-p",
        "atdd.coach.plugins.violation_collector",
        f"--rootdir={repo_root}",
    ]
    argv.extend(str(p) for p in validator_paths)
    return argv


def _build_env(
    *,
    sha: str,
    runtime_dir: Path,
    extra_env: Optional[Mapping[str, str]],
) -> dict[str, str]:
    """Assemble the subprocess env per validator-invocation.md §2 + §5."""
    env: dict[str, str] = {
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "ATDD_VALIDATION_SHA": sha,
        "ATDD_RUNTIME_DIR": str(runtime_dir),
    }
    for key in _ENV_PASSTHROUGH:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    # Per §5: ATDD_VALIDATOR_TIMEOUT_<PHASE> is forwarded verbatim when set.
    for key, value in os.environ.items():
        if key.startswith("ATDD_VALIDATOR_TIMEOUT_"):
            env[key] = value
    # Per §5: GITHUB_TOKEN is forwarded only on opt-in. Coach's caller signals
    # opt-in via extra_env; we never forward it from the ambient environment.
    if extra_env:
        env.update(extra_env)
    return env


__all__ = ["DispatchResult", "dispatch_validators"]
