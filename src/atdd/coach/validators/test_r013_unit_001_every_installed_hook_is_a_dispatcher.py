# URN: test:govern-lifecycle:govern-lifecycle:R013-UNIT-001
# Acceptance: acc:govern-lifecycle:R013-UNIT-001-every-installed-hook-is-a-dispatcher
# WMBT: wmbt:govern-lifecycle:R013
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""R013-UNIT-001 — every installed hook is a dispatcher, none is a frozen copy.

`_refresh_hook_files` (#1492) writes a fixed-content dispatcher for every hook,
with no exceptions. Five tracked hooks are still snapshots of their templates, so
the repo asserts both models at once and the contradiction only surfaces when
someone runs `atdd upgrade` — which rewrites those tracked files underneath them.

Measured in atdd-hooklab against real venvs, real installs and real commits, a
snapshot is worse on both counts that matter:

  * FROZEN — a repo on a snapshot still ran the old hook after upgrading to a
    toolkit whose hook had changed. `atdd init --force` was the only refresh path
    and it is forbidden (#793), which is why six hooks were never installed at all.
  * FAIL-OPEN — with no toolkit on PATH a snapshot ran and exited 0, reporting a
    pass for gates it never computed. A dispatcher exits 1. That is the
    `claude-pre-tool-use.sh` defect, structural in the snapshot model.

A frozen gate that also passes vacuously neither protects nor announces that it
stopped, which is the worst of the four combinations available.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import atdd

pytestmark = [pytest.mark.coach, pytest.mark.platform]

_PKG_DIR = Path(atdd.__file__).resolve().parent
_REPO_ROOT = _PKG_DIR.parents[1]
_INSTALLED_DIR = _REPO_ROOT / ".atdd" / "hooks"
# `coach/templates`, not `templates`: the first draft of this test pointed at a
# directory that does not exist, so `is_file()` was always False and the
# copy-detection assertion passed against an empty set — vacuous, and green.
_TEMPLATE_DIR = _PKG_DIR / "coach" / "templates" / "hooks"

#: The fixed marker every dispatcher carries (hook-dispatcher.sh, #1492).
_DISPATCHER_MARK = "ATDD managed hook dispatcher"


def _installed_hooks() -> list[Path]:
    if not _INSTALLED_DIR.is_dir():
        pytest.skip("no installed hooks in this checkout")
    return sorted(p for p in _INSTALLED_DIR.iterdir() if p.is_file())


def test_r013_unit_001_every_installed_hook_is_a_dispatcher():
    snapshots = [
        p.name for p in _installed_hooks()
        if _DISPATCHER_MARK not in p.read_text(encoding="utf-8", errors="replace")
    ]
    assert snapshots == [], (
        "these installed hooks are still snapshots of their templates:\n  "
        + "\n  ".join(snapshots)
        + "\n\nA snapshot is frozen at install AND fails open when the toolkit is "
        "absent — measured in atdd-hooklab. The installer already writes a "
        "dispatcher for every hook, so each of these is a tracked file that the "
        "next `atdd upgrade` will rewrite underneath whoever runs it."
    )


def test_r013_unit_001_no_installed_hook_is_a_copy_of_its_template():
    """The positive form: byte-identity with a template is now the defect."""
    copies = []
    for p in _installed_hooks():
        tmpl = _TEMPLATE_DIR / p.name
        if tmpl.is_file() and tmpl.read_bytes() == p.read_bytes():
            copies.append(p.name)
    assert copies == [], (
        "installed hooks that are byte-identical copies of their templates: "
        f"{copies}. That was the invariant this migration retires — it is what "
        "froze them and what made every upgrade dirty the working tree."
    )
