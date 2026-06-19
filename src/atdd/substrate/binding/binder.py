"""Provider-spawn execution of a bound implementation (WMBT E001).

The binder executes a bound implementation by PROVIDER-SPAWN: it launches a child
``python`` process that adds the workspace provider's adapter directory to
``sys.path``, imports the provider's own ``run`` adapter, and calls
``run_implementation`` — which itself runs the implementation under the provider's
runtime (for python-pytest: a ``pytest`` subprocess). The child prints the result
as a single tagged JSON line; this module parses it.

So CORE imports neither the extension nor the provider adapter — only the child
process does — and a crashing or side-effecting implementation cannot corrupt the
core process. Violations come back over the provider contract shape
(``[{rule_id, location, evidence}]``).
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Sentinel prefixing the child's single result line, so provider/pytest chatter on
# stdout never collides with the structured payload.
_RESULT_TAG = "__ATDD_BIND_RESULT__"

# Default wall-clock ceiling for a single provider-spawn (seconds); a hang past
# this is a bind failure (M001 fail-safe territory), not a silent pass.
DEFAULT_TIMEOUT_S = 300

_BOOTSTRAP = """\
import json, sys
sys.path.insert(0, {adapter_dir!r})
import run
r = run.run_implementation({impl_id!r}, {test_path!r})
print({tag!r} + json.dumps({{
    "ran": bool(getattr(r, "ran", True)),
    "exit_code": int(getattr(r, "exit_code", 0)),
    "violations": list(getattr(r, "violations", [])),
}}))
"""


@dataclass
class SpawnResult:
    """Outcome of provider-spawning one bound implementation."""

    implementation_id: str
    ran: bool
    exit_code: int
    violations: list[dict] = field(default_factory=list)
    stdout: str = ""
    error: str | None = None  # set when the spawn itself failed (crash/timeout/garbled)


def provider_spawn(
    *,
    adapter_dir: str | Path,
    implementation_id: str,
    test_path: str | Path,
    env: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> SpawnResult:
    """Provider-spawn an implementation via the provider's run adapter (subprocess).

    Launches ``python -c <bootstrap>`` so the provider adapter is imported in the
    CHILD, never in core. Returns a ``SpawnResult``; on crash (no parseable
    result), timeout, or malformed output, ``ran`` is False and ``error`` is set
    (the M001 fail-safe signal) rather than reporting a falsely-clean gate.
    """
    code = _BOOTSTRAP.format(
        adapter_dir=str(adapter_dir),
        impl_id=implementation_id,
        test_path=str(test_path),
        tag=_RESULT_TAG,
    )
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return SpawnResult(
            implementation_id=implementation_id,
            ran=False,
            exit_code=-1,
            error=f"provider-spawn timed out after {timeout}s",
        )

    stdout = proc.stdout or ""
    payload = _parse_result(stdout)
    if payload is None:
        return SpawnResult(
            implementation_id=implementation_id,
            ran=False,
            exit_code=proc.returncode,
            stdout=stdout + (proc.stderr or ""),
            error="provider-spawn produced no parseable result line",
        )
    return SpawnResult(
        implementation_id=implementation_id,
        ran=bool(payload.get("ran", False)),
        exit_code=int(payload.get("exit_code", proc.returncode)),
        violations=list(payload.get("violations", [])),
        stdout=stdout,
    )


def _parse_result(stdout: str) -> dict | None:
    """Extract the single tagged JSON result line the bootstrap prints, if any."""
    for line in reversed(stdout.splitlines()):
        if line.startswith(_RESULT_TAG):
            try:
                return json.loads(line[len(_RESULT_TAG):])
            except json.JSONDecodeError:
                return None
    return None
