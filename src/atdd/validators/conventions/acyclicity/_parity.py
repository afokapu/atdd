"""Real-repo fault-injection helpers for the acyclicity variant.

The filesystem mutations live HERE (a non-`test_*` helper) so the variant test file
stays free of direct filesystem operations (tester.test-isolation guard). The injection
touches the real ``plan/`` tree because the composed graph loader reads it directly, so
``tmp_path`` is not an option — hence the helper + guaranteed revert.

The legacy subprocess oracle (``run_legacy``/``LEGACY_NODEID``) was dropped with the
retired legacy validator (#1207 sweep, #1385); the convention path is the live coverage.
"""
from __future__ import annotations

import contextlib
import shutil
from pathlib import Path


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
