"""Pytest plugin: structured diagnostics artifact (issue #449).

Loaded by ``atdd validate`` via argv injection
(``-p atdd.coach.plugins.diagnostics``). NEVER auto-loaded via
``conftest.py`` or ``pytest_plugins`` — that would leak diagnostics
emission into consumer test suites running outside ``atdd validate``.

Behavior:
  * Tracks active nodeid for each test (so ``fail_with_diagnostic`` can
    record findings against the right test).
  * Captures every failed test's structured ``Finding`` (when migrated)
    or synthesizes an ``unmigrated``-category Finding from
    ``report.longrepr`` text (when not migrated).
  * Detects ``FileNotFoundError`` whose missing path lives inside the
    installed ``atdd`` package directory and surfaces it as a
    toolkit-packaging issue (separate from per-validator findings).
  * Writes ``.atdd/diagnostics/validation/<phase>.yaml`` at session
    finish — but ONLY on the master under xdist (worker processes
    short-circuit) and ONLY when not disabled via env.
  * Prints a stdout summary (only when ``failed > 0``) after pytest's
    own summary.

Disabled when:
  * ``ATDD_DIAGNOSTICS_DISABLED`` env var is set (e.g. by the runner
    when ``--verify-baseline`` is in effect).
  * Running on an xdist worker (``session.config.workerinput`` truthy).
"""

from __future__ import annotations

import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import yaml

import atdd
from atdd.coach.utils.diagnostics import (
    Finding,
    Item,
    LEGAL_CATEGORIES,
    clear_pending_findings,
    get_pending_findings,
    set_active_nodeid,
)
from atdd.coach.utils.repo import find_repo_root


logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Categories that auto-classify based on validator-path keywords. Used as a
# best-effort hint for unmigrated validators so the [<category>] stdout
# bucket isn't 100% [unmigrated]. Validators that have migrated to
# ``fail_with_diagnostic`` set their own category and bypass this map.
_PATH_CATEGORY_HINTS = (
    ("naming", "naming"),
    ("boundary", "boundary"),
    ("boundaries", "boundary"),
    ("syspath", "hygiene"),
    ("contract", "contract"),
    ("hygiene", "hygiene"),
    ("quality", "quality"),
    ("metric", "quality"),
    ("train", "train"),
    ("workflow", "workflow"),
    ("convention", "convention"),
)


# ---------------------------------------------------------------------------
# Plugin state — single instance per pytest session.
# ---------------------------------------------------------------------------


class _DiagnosticsState:
    def __init__(self) -> None:
        # Default to time.time() so that if anyone resets the state mid-
        # session (toolkit-self dogfood, tests), duration_seconds doesn't
        # blow up to ``time.time() - 0.0``. pytest_sessionstart still
        # overwrites this with the real session start.
        self.start_time: float = time.time()
        self.findings: List[Finding] = []
        self.toolkit_packaging_issues: List[Dict[str, Any]] = []
        # Counts mirror pytest's terminal summary so the artifact is
        # self-describing without re-parsing stdout.
        self.passed: int = 0
        self.failed: int = 0
        self.skipped: int = 0
        self.deselected: int = 0
        self.errors: int = 0


_STATE = _DiagnosticsState()


# ---------------------------------------------------------------------------
# Toolkit-packaging detection.
# ---------------------------------------------------------------------------


def _atdd_pkg_dir() -> Path:
    return Path(atdd.__file__).resolve().parent


def _is_toolkit_packaging_issue(filename: Optional[str]) -> bool:
    """True iff *filename* resolves to a path under the installed atdd pkg.

    Decision #5 (refined): substring matching on path strings is forbidden
    because consumer tmp paths can contain ``atdd``. We resolve the path
    (handling symlinks) and use ``Path.is_relative_to`` (Python 3.10+).
    """
    if not filename:
        return False
    try:
        target = Path(filename).resolve()
    except (OSError, ValueError) as exc:
        # Bogus path (NUL byte, symlink loop, etc.) — not a toolkit
        # resource by definition. Returning False is the only sensible
        # answer; raising would mask the actual test failure.
        #
        # But "the answer is False" is not the same as "nothing happened":
        # a path this classifier could not resolve is the one case where its
        # verdict is a fallback rather than a measurement, and nothing else in
        # this plugin records that. `return False` alone leaves no trace, which
        # is precisely what coder.logging.coach-silent-swallow asks about — so
        # this logs instead of carrying an inline suppression past its deadline
        # (#1756; the same fix #1735 applied to approve_command.py).
        # `candidate_path`, not `filename`: `filename` is a reserved LogRecord
        # attribute and `extra` may not overwrite one — logging raises KeyError,
        # which would turn this returns-False path into a crash.
        logger.warning(
            "toolkit-packaging classification fell back to False: the path "
            "could not be resolved",
            extra={"candidate_path": filename, "error": str(exc)},
        )
        return False
    pkg = _atdd_pkg_dir()
    return target.is_relative_to(pkg)


_FNFE_FILENAME_RE = re.compile(r"FileNotFoundError.*?'([^']+)'", re.DOTALL)


def _extract_fnfe_filename(longrepr: Any) -> Optional[str]:
    """Best-effort recover of the missing path from a FileNotFoundError repr.

    Pytest's ``longrepr`` is either a ``ReprExceptionInfo`` or a string;
    we coerce to ``str(longrepr)`` and pattern-match. ``Errno 2`` reprs
    embed the filename inside single-quotes after ``FileNotFoundError``.
    """
    text = str(longrepr) if longrepr is not None else ""
    match = _FNFE_FILENAME_RE.search(text)
    if match:
        return match.group(1)
    return None


# ---------------------------------------------------------------------------
# Pytest hooks.
# ---------------------------------------------------------------------------


def pytest_sessionstart(session: pytest.Session) -> None:
    if _is_disabled():
        return
    _STATE.start_time = time.time()
    _STATE.findings = []
    _STATE.toolkit_packaging_issues = []
    _STATE.passed = 0
    _STATE.failed = 0
    _STATE.skipped = 0
    _STATE.deselected = 0
    _STATE.errors = 0
    clear_pending_findings()


def pytest_runtest_setup(item: pytest.Item) -> None:
    if _is_disabled():
        return
    set_active_nodeid(item.nodeid)


def pytest_runtest_teardown(item: pytest.Item) -> None:
    if _is_disabled():
        return
    set_active_nodeid(None)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Capture per-call results into the session counters + finding list."""
    if _is_disabled():
        return
    # Tally outcomes from the call phase only (setup/teardown errors are
    # counted via the ``failed`` bucket of their respective phase too).
    if report.when == "call":
        if report.passed:
            _STATE.passed += 1
        elif report.failed:
            _STATE.failed += 1
            _record_failure(report)
        elif report.skipped:
            _STATE.skipped += 1
    elif report.when in ("setup", "teardown") and report.failed:
        _STATE.errors += 1
        _record_failure(report)


def pytest_deselected(items: List[pytest.Item]) -> None:
    if _is_disabled():
        return
    _STATE.deselected += len(items)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Write the diagnostics artifact + print stdout summary on the master."""
    if _is_disabled():
        return
    # xdist workers forward reports to the master; only the master writes
    # the artifact. ``workerinput`` is set by xdist on each worker config.
    if getattr(session.config, "workerinput", None) is not None:
        return

    repo_root = find_repo_root()
    phase = _detect_phase(session)

    artifact_path = _diagnostics_path(repo_root, phase)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    duration = time.time() - _STATE.start_time
    document = _build_document(phase=phase, duration=duration)
    artifact_path.write_text(yaml.safe_dump(document, default_flow_style=False, sort_keys=False))

    if _STATE.failed > 0 or _STATE.errors > 0:
        try:
            _print_summary(artifact_path)
        except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow)
            # Never let summary failure mask the test outcome.
            pass


# ---------------------------------------------------------------------------
# Internals.
# ---------------------------------------------------------------------------


def _is_disabled() -> bool:
    """Whether the plugin should short-circuit (env-controlled by the runner)."""
    return os.environ.get("ATDD_DIAGNOSTICS_DISABLED") == "1"


def _record_failure(report: pytest.TestReport) -> None:
    """Look for migrated-validator findings; synthesize an unmigrated one if not."""
    nodeid = report.nodeid

    # Toolkit-packaging detection — runs even when the validator migrated.
    fnfe_path = _extract_fnfe_filename(report.longrepr)
    if fnfe_path and _is_toolkit_packaging_issue(fnfe_path):
        # De-dup by (resource, validator).
        entry = {"resource": fnfe_path, "referenced_by": [nodeid]}
        existing = next(
            (e for e in _STATE.toolkit_packaging_issues if e["resource"] == fnfe_path),
            None,
        )
        if existing is None:
            _STATE.toolkit_packaging_issues.append(entry)
        elif nodeid not in existing["referenced_by"]:
            existing["referenced_by"].append(nodeid)

    pending = get_pending_findings(nodeid)
    if pending:
        _STATE.findings.extend(pending)
        return

    # Synthesize an unmigrated finding from the longrepr text.
    raw = str(report.longrepr) if report.longrepr is not None else ""
    summary = _first_meaningful_line(raw)
    validator_id = nodeid.rsplit("::", 1)[-1] if "::" in nodeid else nodeid
    validator_path = nodeid.split("::", 1)[0] if "::" in nodeid else None
    category = _hint_category_from_path(validator_path) or "unmigrated"

    _STATE.findings.append(
        Finding(
            validator_id=validator_id,
            validator_path=validator_path,
            category=category,
            severity="error",
            summary=summary,
            raw_message=raw,
            items=[],
            convention_ref=None,
        )
    )


def _first_meaningful_line(text: str) -> str:
    """First non-empty line of a longrepr, trimmed to ~140 chars."""
    for line in text.splitlines():
        s = line.strip().lstrip("E ").strip()
        if s and not s.startswith(">") and not s.startswith("_") and not s.startswith("-"):
            return s[:140]
    return (text.strip() or "<no message>")[:140]


def _hint_category_from_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    lowered = path.lower()
    for needle, category in _PATH_CATEGORY_HINTS:
        if needle in lowered:
            return category
    return None


def _detect_phase(session: pytest.Session) -> str:
    """Resolve the validator phase from the session's collected items.

    Looks at the first segment after ``src/atdd/`` in any test path. If
    the run spans multiple phases, returns ``"all"``.
    """
    phases: set[str] = set()
    for arg in session.config.args:
        for name in ("planner", "tester", "coder", "coach"):
            if f"/{name}/validators" in str(arg) or str(arg).endswith(f"/{name}/validators"):
                phases.add(name)
                break
    if len(phases) == 1:
        return next(iter(phases))
    if len(phases) > 1:
        return "all"

    # Fallback: inspect collected items.
    for item in session.items:
        path = str(getattr(item, "fspath", "") or item.nodeid)
        for name in ("planner", "tester", "coder", "coach"):
            if f"/{name}/validators" in path:
                phases.add(name)
                break
    if len(phases) == 1:
        return next(iter(phases))
    if len(phases) > 1:
        return "all"
    return "all"


def _diagnostics_path(repo_root: Path, phase: str) -> Path:
    return repo_root / ".atdd" / "diagnostics" / "validation" / f"{phase}.yaml"


def _invocation_string() -> str:
    return " ".join([os.path.basename(sys.argv[0])] + sys.argv[1:])


def _build_document(phase: str, duration: float) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run": {
            "phase": phase,
            "ran_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration_seconds": round(duration, 2),
            "atdd_version": atdd.__version__,
            "invocation": _invocation_string(),
            "outcome": {
                "passed": _STATE.passed,
                "failed": _STATE.failed + _STATE.errors,
                "skipped": _STATE.skipped,
                "deselected": _STATE.deselected,
            },
        },
        "findings": [f.to_dict() for f in _STATE.findings],
        "toolkit_packaging_issues": list(_STATE.toolkit_packaging_issues),
    }


def _print_summary(artifact_path: Path) -> None:
    findings = _STATE.findings
    if not findings:
        return

    by_category: Dict[str, List[Finding]] = {}
    for f in findings:
        by_category.setdefault(f.category, []).append(f)

    total_findings = len(findings)
    total_categories = len(by_category)

    out = sys.stdout
    out.write(f"\n=== DIAGNOSTICS ({total_findings} findings, {total_categories} categories) ===\n")

    # Stable ordering: alphabetical by category name. Items column is the
    # sum of items across the bucket (not just findings).
    for category in sorted(by_category):
        bucket = by_category[category]
        item_total = sum(max(len(f.items), 1) for f in bucket)
        out.write(
            f"[{category:<14}] {len(bucket):>2} finding{'s' if len(bucket) != 1 else ' '},"
            f" {item_total:>3} item{'s' if item_total != 1 else ''}\n"
        )

    # Top fixes — capped at 10 lines, ordered by category name then file.
    out.write("\nTop fixes (sorted by category, capped at 10):\n")
    printed = 0
    for category in sorted(by_category):
        for finding in by_category[category]:
            if printed >= 10:
                break
            for item in finding.items[:1]:
                if printed >= 10:
                    break
                location = item.file or "(no file)"
                if item.line:
                    location = f"{location}:{item.line}"
                fix_text = item.fix or finding.summary
                out.write(f"  {location}\n    {fix_text}\n")
                printed += 1
            else:
                if not finding.items and printed < 10:
                    out.write(f"  ({finding.validator_path or 'unknown'})\n    {finding.summary}\n")
                    printed += 1
        if printed >= 10:
            break

    try:
        rel = artifact_path.relative_to(find_repo_root())
        location_str = str(rel)
    except ValueError:
        location_str = str(artifact_path)
    out.write(
        f"\nFull diagnostics: {location_str} ({total_findings} finding"
        f"{'s' if total_findings != 1 else ''})\n"
    )
    if _STATE.toolkit_packaging_issues:
        out.write(
            f"Toolkit packaging issues: {len(_STATE.toolkit_packaging_issues)} (see file)\n"
        )
    out.flush()


__all__ = [
    "SCHEMA_VERSION",
]
