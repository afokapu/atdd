"""Run half of the python-pytest provider contract (contract_version 1.1.0).

Execute discovered implementations inside the materialized workspace instance
with the provider command (``pytest``) and translate the result into the ATDD
violation-output contract. v1.1.0 adds two things over v1.0.0 (see
PROVIDER-CONTRACT-v1.1.md):

  * SCAN-MOUNT (§2) — the code-under-inspection is supplied explicitly, never
    auto-discovered. ``run_implementation`` injects ``ATDD_SCAN_ROOTS`` (JSON
    list) and ``ATDD_SCAN_EXCLUDES`` (JSON list) into the subprocess env. The
    detector obeys them; it never calls ``find_repo_root`` or reads
    ``.atdd/config.yaml``.

  * STRUCTURED REPORT CHANNEL (§3) — the provider allocates a temp report path,
    passes it as ``ATDD_VIOLATIONS_REPORT``, runs pytest, then reads back a JSON
    report of RAW ``{rule_id,file,line,col,evidence,source_line}`` violations.
    One run may carry many ``file:line:col`` sites under MULTIPLE distinct
    ``rule_id``s.

The provider performs ZERO disposition logic. ``violations`` is the RAW factual
channel; the disposition verdict (strict / suppress-and-clean / advisory) is the
downstream consumer's job (§1). ``passed``/``exit_code`` is RUN-HEALTH, not a
verdict.

BACK-COMPAT (§4): the report channel is opt-in. An implementation that writes no
report (the Phase-0 ``coder.logging.print`` detector) falls through to the
identical v1.0.0 exit-code → single ``{rule_id=impl_id, location="."}`` mapping.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

CONTRACT_VERSION = "1.1.0"
RUN_COMMAND = (sys.executable, "-m", "pytest")

# Env-var channel names (shared verbatim with the detector; documented in the
# contract so any v1.1 implementation can rely on them).
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"        # JSON list[str] — code-under-inspection roots
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"  # JSON list[str] — exclusion globs
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"     # path the detector writes its JSON report to

# pytest exit codes (pytest.ExitCode) the contract distinguishes.
_EXIT_OK = 0
_EXIT_TESTS_FAILED = 1

# Required keys on a v1.1 structured violation record.
_VIOLATION_KEYS = ("rule_id", "file", "line", "col", "evidence", "source_line")


@dataclass(frozen=True)
class RunResult:
    """Outcome of running one implementation's tests under the provider.

    ``violations`` is the RAW factual channel — the provider applies no
    disposition. ``passed`` / ``exit_code`` is run-health (did the detector
    execute and emit), NOT a pass/fail verdict; the verdict is computed
    downstream from ``violations`` by the consumer.
    """

    implementation_id: str
    passed: bool
    exit_code: int
    violations: list[dict] = field(default_factory=list)
    stdout: str = ""
    structured: bool = False  # True when violations came from the v1.1 report channel

    @property
    def ran(self) -> bool:
        """True when pytest actually collected and executed (not a usage error)."""
        return self.exit_code in (_EXIT_OK, _EXIT_TESTS_FAILED)


def _fallback_violations(exit_code: int, stdout: str, implementation_id: str) -> list[dict]:
    """v1.0.0 mapping: a failing run → one impl-keyed violation at root location.

    Used only when the implementation emits no structured report (back-compat for
    v1.0.0 strict detectors like ``coder.logging.print``). A passing run yields
    none.
    """
    if exit_code == _EXIT_OK:
        return []
    summary = stdout.strip().splitlines()[-1] if stdout.strip() else f"exit {exit_code}"
    return [{"rule_id": implementation_id, "location": ".", "evidence": summary}]


def _read_report(report_path: Path) -> list[dict] | None:
    """Read + validate the structured report, or None if absent/malformed.

    Returning None routes the caller to the v1.0.0 fallback — a malformed report
    must never be silently treated as "zero violations" (that would hide a
    detector bug as a clean pass).
    """
    if not report_path.is_file():
        return None
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("violations")
    if not isinstance(raw, list):
        return None
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        if not all(k in item for k in _VIOLATION_KEYS):
            return None
        out.append(item)
    return out


def run_implementation(
    implementation_id: str,
    test_path: str | Path,
    *,
    scan_roots: list[str] | None = None,
    exclude_globs: list[str] | None = None,
    env: dict | None = None,
) -> RunResult:
    """Run pytest over ``test_path`` and return a contract-shaped result.

    ``test_path`` is a file or directory inside the resolved workspace instance.
    ``scan_roots`` / ``exclude_globs`` are the explicit scan-mount inputs (§2) —
    injected as JSON env vars for the detector to obey. The provider command is
    ``python -m pytest`` so the interpreter that resolved the instance runs it.

    The provider injects ``ATDD_VIOLATIONS_REPORT``; if the detector writes a
    valid v1.1 report there, those RAW violations are returned (``structured=
    True``). Otherwise the v1.0.0 exit-code fallback applies (``structured=
    False``).
    """
    base_env = dict(env if env is not None else os.environ)
    if scan_roots is not None:
        base_env[ENV_SCAN_ROOTS] = json.dumps([str(r) for r in scan_roots])
    if exclude_globs is not None:
        base_env[ENV_SCAN_EXCLUDES] = json.dumps([str(g) for g in exclude_globs])

    with tempfile.TemporaryDirectory(prefix="atdd-pyp-report-") as tmp:
        report_path = Path(tmp) / "violations.json"
        base_env[ENV_REPORT] = str(report_path)

        cmd = [*RUN_COMMAND, "--tb=no", "-q", str(test_path)]
        proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
            cmd, capture_output=True, text=True, env=base_env
        )
        stdout = proc.stdout + proc.stderr

        structured_violations = _read_report(report_path)

    if structured_violations is not None:
        # v1.1 structured channel: RAW violations come from the report. passed is
        # run-health (exit 0), NOT a disposition verdict.
        return RunResult(
            implementation_id=implementation_id,
            passed=proc.returncode == _EXIT_OK,
            exit_code=proc.returncode,
            violations=structured_violations,
            stdout=stdout,
            structured=True,
        )

    # v1.0.0 fallback: exit-code → single impl-keyed violation.
    return RunResult(
        implementation_id=implementation_id,
        passed=proc.returncode == _EXIT_OK,
        exit_code=proc.returncode,
        violations=_fallback_violations(proc.returncode, stdout, implementation_id),
        stdout=stdout,
        structured=False,
    )
