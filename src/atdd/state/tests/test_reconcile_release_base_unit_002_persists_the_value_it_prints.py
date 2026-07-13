# URN: test:govern-lifecycle:state:reconcile-release-base-unit-persists-the-value-it-prints
# Issue: #1449
# Phase: RED
# Layer: application
# Assertion: behavioral
"""#1449 — ``reconcile-base`` must never print a value it did not write.

The lived bug::

    $ atdd state version reconcile-base --git-tag 4.5.1
    4.5.1                        # <- prints the right answer
    $ atdd state version show
    Release version: 4.0.1       # <- store UNCHANGED

Every reconcile *looked* successful and persisted nothing, so the Store drifted
five minor versions behind PyPI. ``reconcile-base`` computed the base and left
the write to a separate ``set`` — a footgun the command's own name disproves.

It now persists. Two contracts constrain the fix:

- stdout stays a BARE version string — ``publish.yml`` captures it with
  ``BASE=$(atdd state version reconcile-base ...)``; any chatter on stdout would
  poison the release. Confirmations go to stderr.
- if the store cannot be written, it exits non-zero and prints NOTHING to
  stdout, rather than reporting a success that did not happen.

Hermetic: every case drives a throwaway Control Root via ``--root``. Never the
real shared store — a leak here would regress the live release version.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from atdd.state.cli import run

_SRC = Path(__file__).resolve().parents[3]


def _mk_root(path: Path) -> Path:
    """A throwaway Control Root (the State Store inits lazily on first open)."""
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    (path / ".atdd").mkdir(parents=True, exist_ok=True)
    (path / ".atdd" / "config.yaml").write_text("x\n", encoding="utf-8")
    return path


@pytest.fixture()
def root(tmp_path) -> Path:
    return _mk_root(tmp_path / "repo")


def test_reconcile_base_persists_and_show_reads_it_back(root, capsys):
    """#1449 acceptance (iii): reconcile-base X → `version show` reads back X."""
    assert run(["version", "reconcile-base", "--git-tag", "4.5.2",
                "--no-pypi", "--root", str(root)]) == 0
    capsys.readouterr()

    assert run(["version", "show", "--root", str(root)]) == 0
    assert "Release version: 4.5.2" in capsys.readouterr().out


def test_stdout_is_the_bare_version_for_publish_yml_command_substitution(root, capsys):
    """publish.yml does BASE=$(... reconcile-base ...) — stdout must stay bare."""
    assert run(["version", "reconcile-base", "--git-tag", "4.5.2",
                "--no-pypi", "--root", str(root)]) == 0
    assert capsys.readouterr().out.strip() == "4.5.2"


def test_unwritable_store_fails_loudly_and_prints_no_version(tmp_path, capsys):
    """No Control Root → exit non-zero, and NOTHING on stdout.

    The cardinal rule: never print a value we did not write.
    """
    orphan = tmp_path / "nowhere"
    orphan.mkdir()

    rc = run(["version", "reconcile-base", "--git-tag", "4.5.2",
              "--no-pypi", "--root", str(orphan)])
    out = capsys.readouterr().out

    assert rc != 0, "an unwritable store must fail loudly, not silently no-op"
    assert "4.5.2" not in out, (
        "reconcile-base printed a version it did not persist — the exact lie "
        "that drifted the Store five minor versions behind PyPI"
    )


def test_reconcile_base_persists_live_end_to_end(root):
    """The real installed-form CLI, in a real subprocess, against a real store."""
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""),
           "HOME": str(root), "CI": "true"}

    def _cli(*args):
        return subprocess.run(
            [sys.executable, "-m", "atdd", "state", "version", *args,
             "--root", str(root)],
            cwd=str(root), env=env, capture_output=True, text=True, timeout=60,
        )

    r = _cli("reconcile-base", "--git-tag", "4.5.2", "--no-pypi")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "4.5.2"

    r = _cli("show")
    assert r.returncode == 0, r.stderr
    assert "Release version: 4.5.2" in r.stdout, (
        f"reconcile-base did not persist across processes: {r.stdout!r}"
    )
