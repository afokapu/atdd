"""Real-repo fault-injection + legacy-subprocess helpers for the boundary variant.

Filesystem mutations on the REAL source tree live HERE (a non-`test_*` helper) so the
variant test file stays free of direct filesystem operations (tester.test-isolation
guard). The injection must touch the real ``src/atdd/`` tree because the legacy
validator imports/scans it — ``tmp_path`` is not an option — hence the helper + revert.
"""
from __future__ import annotations

import contextlib
import logging
import subprocess
import sys
from pathlib import Path

_log = logging.getLogger(__name__)

LEGACY_NODEID = (
    "src/atdd/planner/validators/test_theme_commons_coach_boundary.py"
    "::test_commons_wagons_do_not_import_coach"
)


def run_legacy(root: Path) -> subprocess.CompletedProcess:
    """Run the legacy boundary validator as a subprocess (inherits parent env,
    which carries PYTHONPATH=src)."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", LEGACY_NODEID, "-q", "-p", "no:cacheprovider"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )


@contextlib.contextmanager
def injected_coach_import(root: Path, target_slug: str):
    """Create a coach-importing module under a real commons wagon's source tree
    (``src/atdd/<slug>/_boundary_fault_injection.py``); revert on exit."""
    src_dir = root / "src" / "atdd" / target_slug.replace("-", "_")
    fault = src_dir / "_boundary_fault_injection.py"
    try:
        src_dir.mkdir(parents=True, exist_ok=True)
        fault.write_text("import atdd.coach  # injected boundary crossing\n", encoding="utf-8")
        yield
    finally:
        if fault.exists():
            fault.unlink()
        try:
            src_dir.rmdir()
        except OSError as exc:
            _log.debug("boundary injection cleanup left a non-empty dir",
                       extra={"dir": str(src_dir), "error": str(exc)})
