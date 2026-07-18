# URN: component:project-shared-state:test-support:live_cli:backend:tests
# Runtime: python
# Purpose: Drive the real in-tree `atdd state` CLI by subprocess against a real checkout — the SMOKE harness for project-shared-state.

"""Live-CLI harness for the project-shared-state SMOKE acceptances (#1400).

The SMOKE tests must exercise the *real* command surface against a *real*
checkout and a *real* ``.atdd/state/state.sqlite`` — not an in-process call into
the library. So they build a Control Root under ``tmp_path`` and drive
``python -m atdd state ...`` by subprocess, exactly as an operator would.

``CI=true`` and a ``HOME`` pinned inside ``tmp_path`` keep the run hermetic: it
can neither read nor write the developer's real store.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .._fixtures import make_checkout  # re-exported: the acceptances import it from here

#: The in-tree ``src/`` root, so the subprocess drives THIS working copy's CLI.
_SRC = Path(__file__).resolve().parents[4]


def atdd_state(root: Path, *args: str) -> subprocess.CompletedProcess:
    """Run ``atdd state <args>`` in ``root`` and capture its result."""
    env = {
        "PYTHONPATH": str(_SRC),
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(root),
        "CI": "true",
    }
    return subprocess.run(
        [sys.executable, "-m", "atdd", "state", *args, "--root", str(root)],
        cwd=str(root), env=env, capture_output=True, text=True, timeout=120,
    )
