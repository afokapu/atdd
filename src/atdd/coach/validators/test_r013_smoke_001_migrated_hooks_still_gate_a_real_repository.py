# URN: test:govern-lifecycle:govern-lifecycle:R013-SMOKE-001
# Acceptance: acc:govern-lifecycle:R013-SMOKE-001-migrated-hooks-still-gate-a-real-repository
# WMBT: wmbt:govern-lifecycle:R013
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
# Smoke: true
# # Phase: SMOKE
# # Smoke: true

"""R013-SMOKE-001 — a migrated hook still refuses what it exists to refuse.

The entire risk of this change is disabling enforcement while appearing to tidy
it. A dispatcher that cannot resolve its packaged hook is indistinguishable, from
the outside, from a hook with nothing to say — both let the commit through unless
the dispatcher fails closed. So the proof has to be a real hook refusing a real
`git commit` on a real repository.

Both directions are asserted, because each alone is satisfiable by a broken
migration:

  * RESOLVABLE toolkit -> the commit on main is refused, and the refusal text
    comes from the GATE, not from the dispatcher failing to find anything;
  * UNRESOLVABLE toolkit -> the commit is still refused. This is the property
    the snapshot model did not have: measured in atdd-hooklab, a snapshot with
    nothing on PATH ran and exited 0, reporting a pass it never computed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import atdd

pytestmark = [pytest.mark.coach, pytest.mark.slow, pytest.mark.platform]

_PKG_DIR = Path(atdd.__file__).resolve().parent
_INSTALLED_DIR = _PKG_DIR.parents[1] / ".atdd" / "hooks"


def _repo_on_main(tmp_path: Path) -> Path:
    repo = tmp_path / "consumer"
    (repo / ".atdd").mkdir(parents=True)
    for args in (["init", "-q", "-b", "main"],
                 ["config", "user.email", "t@example.com"],
                 ["config", "user.name", "T"]):
        r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    (repo / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")

    hooks = repo / ".githooks"
    hooks.mkdir()
    shutil.copy2(_INSTALLED_DIR / "pre-commit", hooks / "pre-commit")
    (hooks / "pre-commit").chmod(0o755)
    subprocess.run(["git", "config", "core.hooksPath", ".githooks"],
                   cwd=str(repo), check=True, capture_output=True)
    return repo


def _commit(repo: Path, name: str, *, toolkit_on_path: bool):
    (repo / f"{name}.txt").write_text(name, encoding="utf-8")
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if not toolkit_on_path:
        env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    subprocess.run(["git", "add", "-A"], cwd=str(repo), env=env,
                   check=True, capture_output=True)
    return subprocess.run(["git", "commit", "-m", name], cwd=str(repo), env=env,
                          capture_output=True, text=True)


def test_r013_smoke_001_migrated_hook_refuses_a_commit_on_main(tmp_path):
    if shutil.which("atdd") is None:
        pytest.skip("no resolvable atdd on PATH — cannot exercise the resolvable leg")

    repo = _repo_on_main(tmp_path)
    r = _commit(repo, "onmain", toolkit_on_path=True)

    assert r.returncode != 0, (
        "a migrated pre-commit let a commit onto main through — the hook that "
        f"was supposed to refuse it:\n{r.stdout}{r.stderr}"
    )
    combined = r.stdout + r.stderr
    assert "UNRESOLVABLE" not in combined.upper(), (
        "the commit was refused by the dispatcher failing to resolve, not by the "
        f"gate. That is a broken migration wearing the right exit code:\n{combined}"
    )


def test_r013_smoke_001_migrated_hook_fails_closed_without_the_toolkit(tmp_path):
    """The property the snapshot model lacked: refuse rather than pass vacuously."""
    repo = _repo_on_main(tmp_path)
    r = _commit(repo, "notoolkit", toolkit_on_path=False)

    assert r.returncode != 0, (
        "with no resolvable toolkit the hook let the commit through, reporting a "
        "pass for gates it never computed — the fail-open behaviour this "
        f"migration exists to remove:\n{r.stdout}{r.stderr}"
    )
