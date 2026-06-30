# URN: component:govern-lifecycle:enforcement-substrate:test_prepush_repo_validate_opt_in:backend:domain
# Runtime: python
# Purpose: The LOCAL pre-push hook must NOT run the full `atdd repo validate`
#          URN-graph traversal by default (it is ~2-4 min); it is deferred to
#          CI and made opt-in via ATDD_PREPUSH_FULL=1. Fast local feedback (the
#          planner/tester legs) is preserved; CI stays authoritative (#1254).
"""
Acceptance tests for issue #1254 — trim the heavy `atdd repo validate` leg from
the LOCAL pre-push hook.

Background
----------
For any ``plan/`` or ``contracts/`` change the pre-push hook set ``RUN_REPO=1``
and ran the **full** ``atdd repo validate`` URN-graph traversal **un-skipped**
(every other leg runs ``--local --skip-api``). Measured locally: the full
traversal builds the entire URN graph (~2,900+ URNs) and costs ~2-4 minutes —
the dominant cost of pushing a ``plan/`` change. (A "lighter" sub-command does
NOT help: ``atdd repo broken`` measured at 242s vs ``atdd repo validate`` at
222s — the cost is graph *construction*, not traversal.)

This is NOT issue #934. PR #934 added the ``--skip-api`` env-scrub to the
*validator* legs (``test_runner.py::_scrub_git_hook_env``); it never touched the
hook template nor the ``atdd repo validate`` ``RUN_REPO`` leg.

Design
------
Default: the ``RUN_REPO`` leg **defers** the full URN-graph traversal to CI
(whose ``validate-conventions`` job runs ``resolution/urn_traceability`` over the
real repo graph — authoritative). The ``RUN_PLANNER`` / ``RUN_TESTER`` legs that
fire alongside ``RUN_REPO`` still run ``--local --skip-api``, preserving fast
local feedback. Opt in to the full local traversal with ``ATDD_PREPUSH_FULL=1``.

``ATDD_PREPUSH_FULL`` *adds* validation; it is the opposite of a bypass and is
not an ``ATDD_SKIP_*`` flag, so the E026/E030 bypass-inventory meta-guard is
unaffected.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]
TEMPLATE_HOOK = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "hooks" / "pre-push"
INSTALLED_HOOK = REPO_ROOT / ".atdd" / "hooks" / "pre-push"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True, capture_output=True)
    for k, v in (("user.email", "t@a.test"), ("user.name", "atdd test")):
        subprocess.run(["git", "-C", str(path), "config", k, v], check=True, capture_output=True)


def _add_and_commit(path: Path, rel: str, msg: str) -> str:
    target = path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# placeholder\n")
    subprocess.run(["git", "-C", str(path), "add", rel], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", msg], check=True, capture_output=True)
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def _make_recording_atdd(tmp_path: Path) -> tuple[Path, Path]:
    """A PATH dir with a fake ``atdd`` that records every call (always exits 0) and a
    fake ``python3`` that no-ops the hook's version gate (always exits 0).

    Neutralizing the version gate with a fake ``python3`` keeps the test hermetic:
    it does not depend on the hook's interpreter being able to import the atdd
    package (which it cannot under CI's tmp-repo cwd), so the test exercises the
    blast-radius routing in isolation.
    """
    log_file = tmp_path / "atdd_calls.log"
    bin_dir = tmp_path / f"_fake_bin_{tmp_path.name}"
    bin_dir.mkdir()
    atdd_script = bin_dir / "atdd"
    atdd_script.write_text(f'#!/bin/sh\necho "$@" >> "{log_file}"\nexit 0\n')
    atdd_script.chmod(atdd_script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    py_script = bin_dir / "python3"
    py_script.write_text("#!/bin/sh\nexit 0\n")
    py_script.chmod(py_script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir, log_file


def _run_pre_push(
    repo: Path,
    local_sha: str,
    remote_sha: str,
    *,
    fake_atdd_dir: Path,
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess:
    push_stdin = (
        f"refs/heads/feat/test-1254 {local_sha} refs/heads/feat/test-1254 {remote_sha}\n"
    )
    env = {
        **os.environ,
        "ATDD_SKIP_VERSION_GATE": "1",
        "ATDD_SKIP_BARE_CHECK": "1",
        "PATH": f"{fake_atdd_dir}:{os.environ['PATH']}",
        # deliberately NOT CI=true: the validator section must run
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["sh", str(TEMPLATE_HOOK), "origin", "https://example.invalid/x.git"],
        cwd=str(repo),
        input=push_stdin,
        env=env,
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# AC-3: template ⇄ installed hook stay byte-identical
# ---------------------------------------------------------------------------


def test_template_and_installed_hook_are_byte_identical() -> None:
    """AC-3: the source template and the installed hook must not drift."""
    assert TEMPLATE_HOOK.exists(), f"missing template hook: {TEMPLATE_HOOK}"
    assert INSTALLED_HOOK.exists(), f"missing installed hook: {INSTALLED_HOOK}"
    assert TEMPLATE_HOOK.read_bytes() == INSTALLED_HOOK.read_bytes(), (
        "src/atdd/coach/templates/hooks/pre-push and .atdd/hooks/pre-push "
        "have drifted — regenerate so they are byte-identical."
    )


# ---------------------------------------------------------------------------
# Static source contract: the RUN_REPO leg is gated, not unconditional
# ---------------------------------------------------------------------------


def test_full_repo_validate_is_gated_behind_opt_in_flag() -> None:
    """AC-1/AC-2: `atdd repo validate` in the RUN_REPO leg must be guarded by
    ATDD_PREPUSH_FULL, not invoked unconditionally."""
    text = TEMPLATE_HOOK.read_text(encoding="utf-8")
    assert "ATDD_PREPUSH_FULL" in text, (
        "pre-push hook must gate the full `atdd repo validate` traversal behind "
        "ATDD_PREPUSH_FULL=1 (it is deferred to CI by default)."
    )
    # The opt-in guard must appear before the full traversal invocation.
    flag_idx = text.index("ATDD_PREPUSH_FULL")
    validate_idx = text.index("atdd repo validate")
    assert flag_idx < validate_idx, (
        "the ATDD_PREPUSH_FULL guard must wrap (precede) the `atdd repo validate` call."
    )


def test_opt_in_flag_is_not_a_bypass_flag() -> None:
    """AC-4: ATDD_PREPUSH_FULL is an opt-IN (adds validation), never an ATDD_SKIP_* bypass."""
    text = TEMPLATE_HOOK.read_text(encoding="utf-8")
    assert "ATDD_SKIP_PREPUSH" not in text and "ATDD_SKIP_REPO" not in text, (
        "the trim must not introduce any ATDD_SKIP_* bypass flag."
    )


# ---------------------------------------------------------------------------
# AC-1: default (no ATDD_PREPUSH_FULL) defers the full traversal to CI
# ---------------------------------------------------------------------------


def test_default_plan_push_does_not_run_full_repo_validate(tmp_path: Path) -> None:
    """AC-1: a plan/ push WITHOUT ATDD_PREPUSH_FULL does not invoke `repo validate`,
    but still runs the fast planner leg, and exits 0."""
    fake_dir, log_file = _make_recording_atdd(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    base = _add_and_commit(repo, "README.md", "seed")
    tip = _add_and_commit(repo, "plan/some_wagon/M001.yaml", "edit plan file")

    result = _run_pre_push(repo, tip, base, fake_atdd_dir=fake_dir)

    assert result.returncode == 0, f"default plan push must pass; stderr={result.stderr}"
    calls = log_file.read_text() if log_file.exists() else ""
    assert "repo validate" not in calls, (
        f"default pre-push must NOT run the full `atdd repo validate` traversal; calls:\n{calls}"
    )
    assert "validate planner --local --skip-api" in calls, (
        f"the fast planner leg must still run on plan/ changes; calls:\n{calls}"
    )


# ---------------------------------------------------------------------------
# AC-2: ATDD_PREPUSH_FULL=1 restores the full local traversal
# ---------------------------------------------------------------------------


def test_opt_in_runs_full_repo_validate(tmp_path: Path) -> None:
    """AC-2: with ATDD_PREPUSH_FULL=1, the hook runs the full `atdd repo validate`."""
    fake_dir, log_file = _make_recording_atdd(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    base = _add_and_commit(repo, "README.md", "seed")
    tip = _add_and_commit(repo, "plan/some_wagon/M001.yaml", "edit plan file")

    result = _run_pre_push(
        repo, tip, base, fake_atdd_dir=fake_dir, extra_env={"ATDD_PREPUSH_FULL": "1"}
    )

    assert result.returncode == 0, f"opt-in plan push must pass; stderr={result.stderr}"
    calls = log_file.read_text() if log_file.exists() else ""
    assert "repo validate" in calls, (
        f"ATDD_PREPUSH_FULL=1 must run the full `atdd repo validate`; calls:\n{calls}"
    )


# ---------------------------------------------------------------------------
# AC-5 (SMOKE, live): a real `git push` over a plan/ change is fast under the
# new hook (no full traversal by default), proven through git's own plumbing.
# ---------------------------------------------------------------------------


@pytest.mark.smoke
def test_smoke_real_git_push_of_plan_change_skips_full_traversal(tmp_path: Path) -> None:
    """AC-5-SMOKE: a real `git push` of a plan/ change fires the installed hook and
    does NOT invoke the full `atdd repo validate` traversal by default (fast path),
    while the broken-graph case is still caught authoritatively by CI."""
    fake_dir, log_file = _make_recording_atdd(tmp_path)
    local = tmp_path / "local"
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "-b", "main", str(local)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True, capture_output=True)
    for k, v in (("user.email", "t@a.test"), ("user.name", "atdd test")):
        subprocess.run(["git", "-C", str(local), "config", k, v], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(local), "remote", "add", "origin", str(remote)],
        check=True, capture_output=True,
    )

    # Seed main and push it BEFORE installing the hook (the hook blocks direct
    # pushes to main — mirrors the real install flow).
    (local / "README.md").write_text("hello\n")
    subprocess.run(["git", "-C", str(local), "add", "README.md"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(local), "commit", "-q", "-m", "seed"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(local), "push", "-q", "origin", "main"],
        check=True, capture_output=True,
    )

    # Now install the SOURCE template as the real hook.
    dst = local / ".git" / "hooks" / "pre-push"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(TEMPLATE_HOOK.read_bytes())
    dst.chmod(dst.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # Feature branch with a plan/ change.
    subprocess.run(
        ["git", "-C", str(local), "checkout", "-q", "-b", "feat/1254-smoke"],
        check=True, capture_output=True,
    )
    plan_file = local / "plan" / "some_wagon" / "M001.yaml"
    plan_file.parent.mkdir(parents=True, exist_ok=True)
    plan_file.write_text("# plan edit\n")
    subprocess.run(["git", "-C", str(local), "add", "plan/some_wagon/M001.yaml"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(local), "commit", "-q", "-m", "edit plan"], check=True, capture_output=True)

    env = {
        **os.environ,
        "ATDD_SKIP_VERSION_GATE": "1",
        "ATDD_SKIP_BARE_CHECK": "1",
        "PATH": f"{fake_dir}:{os.environ['PATH']}",
        # NOT CI=true — the validator section must run through real push plumbing
    }
    result = subprocess.run(
        ["git", "-C", str(local), "push", "origin", "feat/1254-smoke"],
        env=env, capture_output=True, text=True,
    )

    assert result.returncode == 0, (
        f"real plan/ push must succeed fast under the new hook; "
        f"rc={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    calls = log_file.read_text() if log_file.exists() else ""
    assert "repo validate" not in calls, (
        f"the live push must NOT trigger the full `atdd repo validate` traversal "
        f"by default (fast local fast-fail); recorded calls:\n{calls}"
    )
    assert "validate planner --local --skip-api" in calls, (
        f"the fast planner leg must still fire on the live plan/ push; calls:\n{calls}"
    )
