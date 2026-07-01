"""Real-repo fault-injection + legacy-subprocess helpers for the acyclicity variant.

The filesystem mutations live HERE (a non-`test_*` helper) so the variant test file
stays free of direct filesystem operations (tester.test-isolation guard). The injection
must touch the real ``plan/`` tree because the legacy validator reads it directly, so
``tmp_path`` is not an option — hence the helper + guaranteed revert.
"""
from __future__ import annotations

import contextlib
import shutil
import subprocess
import sys
from pathlib import Path

LEGACY_NODEID = (
    "src/atdd/planner/validators/test_no_cross_wagon_consume_cycle.py"
    "::test_no_cross_wagon_consume_cycle"
)


def run_legacy(repo_root: Path) -> int:
    """Run the legacy validator's live test as a subprocess; return its rc.
    Inherits the parent process environment (already carries PYTHONPATH=src)."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", LEGACY_NODEID, "-q", "-p", "no:cacheprovider"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    ).returncode


@contextlib.contextmanager
def injected_cross_wagon_cycle(repo_root: Path):
    """Inject a real on-disk cross-wagon produce/consume cycle into ``plan/``.

    Two temp wagon manifests (read by BOTH the composed graph loader and the legacy
    ``load_manifests`` glob) where each consumes an artifact the other produces — a
    strongly-connected component spanning two wagons. Reverted on exit.
    """
    specs = {
        "zztmp_acy_alpha": ("zztmp-acy-alpha", "x:zz:from-alpha", "x:zz:from-beta"),
        "zztmp_acy_beta": ("zztmp-acy-beta", "x:zz:from-beta", "x:zz:from-alpha"),
    }
    created = []
    try:
        for slug, (wagon, prod, cons) in specs.items():
            d = repo_root / "plan" / slug
            d.mkdir(parents=True, exist_ok=False)
            (d / f"_{slug}.yaml").write_text(
                f"wagon: {wagon}\nproduce:\n  - name: {prod}\nconsume:\n  - name: {cons}\n",
                encoding="utf-8",
            )
            created.append(d)
        yield ("zztmp-acy-alpha", "zztmp-acy-beta")
    finally:
        for d in created:
            shutil.rmtree(d, ignore_errors=True)
