# URN: test:govern-lifecycle:hooks-must-not-drift-from-template:H001-INTEGRATION-001-hook-template-change-propagates
# Acceptance: acc:govern-lifecycle:H001-INTEGRATION-001-hook-template-change-propagates
# WMBT: wmbt:govern-lifecycle:H001
# Phase: RED
# Layer: backend.integration
"""AC-INTEGRATION-001: a hook template change reaches the installed hook (#1492).

This is the gate the whole issue exists for. `.atdd/hooks/*` was a snapshot COPY
of the packaged templates, refreshable only by `atdd init --force` (forbidden,
#793) — so every hook fix ever made reached only repos initialised after it
landed, and 6 of 11 hooks were never installed at all.

The installed hook is now a fixed-content dispatcher that execs the PACKAGED
hook, so a template fix propagates with the package and there is no copied logic
left to go stale.

These tests assert BEHAVIOUR, not file contents: they change a packaged hook and
then check that the *new logic actually executes*. A test that only diffed bytes
would pass against a hook that never runs — which is the class of mistake this
program exists to end.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.hooks import declared_hook_names, packaged_hooks_dir
from atdd.coach.commands.initializer import ProjectInitializer

pytestmark = [pytest.mark.coach]

_CANARY = "H001-CANARY-new-logic-executed"


def _fake_atdd_bin(bin_dir: Path, hooks_dir: Path) -> None:
    """Write a stand-in `atdd` implementing only `hooks path <name>`.

    The dispatcher resolves the packaged hook by shelling out to the `atdd`
    console script. Pointing that at a temp hooks dir lets the test mutate a
    "packaged" hook without touching the real installed package or the repo.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "atdd"
    shim.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "hooks" ] && [ "$2" = "path" ]; then\n'
        f'    p="{hooks_dir}/$3"\n'
        '    [ -f "$p" ] || exit 1\n'
        '    printf "%s\\n" "$p"\n'
        "    exit 0\n"
        "fi\n"
        "exit 1\n"
    )
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _install_dispatcher(tmp_path: Path, hook_name: str) -> Path:
    """Install the real dispatcher for *hook_name* into tmp_path/.atdd/hooks."""
    initializer = ProjectInitializer(tmp_path)
    body = initializer._dispatcher_body(hook_name)
    assert body is not None, "dispatcher template missing from the package"
    dst = tmp_path / ".atdd" / "hooks" / hook_name
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(body)
    dst.chmod(dst.stat().st_mode | stat.S_IEXEC)
    return dst


def _run(hook: Path, env_path: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PATH=env_path)
    # /bin/sh absolute: a test may restrict PATH to prove the dispatcher cannot
    # find `atdd`, and that must not also make the interpreter unfindable.
    return subprocess.run(
        ["/bin/sh", str(hook), *args],
        capture_output=True, text=True, timeout=30, env=env, stdin=subprocess.DEVNULL,
    )


def test_packaged_hook_change_executes_without_any_refresh(tmp_path: Path) -> None:
    """The core gate: change the packaged hook, and the NEW logic runs.

    No `atdd init`, no `atdd sync`, no `--force` between the change and the run —
    that is the point. Under the old copy-install this could not pass.
    """
    pkg_hooks = tmp_path / "pkg"
    pkg_hooks.mkdir()
    (pkg_hooks / "commit-msg").write_text("#!/bin/sh\nexit 0\n")

    bin_dir = tmp_path / "bin"
    _fake_atdd_bin(bin_dir, pkg_hooks)
    hook = _install_dispatcher(tmp_path, "commit-msg")
    path = f"{bin_dir}:{os.environ.get('PATH', '')}"

    # Baseline: the dispatcher execs the packaged hook and passes.
    assert _run(hook, path).returncode == 0

    # A hook fix lands in the package (the shape of #1491's guard fix).
    (pkg_hooks / "commit-msg").write_text(
        f'#!/bin/sh\necho "{_CANARY}" >&2\nexit 1\n'
    )

    result = _run(hook, path)
    assert _CANARY in result.stderr, (
        "The changed packaged hook did NOT execute — a hook fix would reach "
        f"nobody (#1492). stderr={result.stderr!r}"
    )
    assert result.returncode == 1, "the new logic's exit status was not honoured"


def test_dispatcher_passes_arguments_through(tmp_path: Path) -> None:
    """Args must survive the dispatcher: commit-msg receives $1 = message file."""
    pkg_hooks = tmp_path / "pkg"
    pkg_hooks.mkdir()
    (pkg_hooks / "commit-msg").write_text('#!/bin/sh\necho "ARG=$1" >&2\nexit 0\n')
    bin_dir = tmp_path / "bin"
    _fake_atdd_bin(bin_dir, pkg_hooks)
    hook = _install_dispatcher(tmp_path, "commit-msg")

    result = _run(hook, f"{bin_dir}:{os.environ.get('PATH', '')}", "/tmp/COMMIT_EDITMSG")
    assert "ARG=/tmp/COMMIT_EDITMSG" in result.stderr, (
        f"dispatcher dropped the hook's arguments: {result.stderr!r}"
    )


def test_dispatcher_fails_closed_when_atdd_is_unresolvable(tmp_path: Path) -> None:
    """A guard that cannot run must BLOCK, never silently allow.

    Silently allowing is the claude-pre-tool-use.sh defect, which fail-opens on a
    missing classifier and is therefore inert in every consumer repo.
    """
    hook = _install_dispatcher(tmp_path, "commit-msg")
    empty_bin = tmp_path / "emptybin"
    empty_bin.mkdir()

    result = _run(hook, str(empty_bin))  # no `atdd` anywhere on PATH
    assert result.returncode != 0, (
        "dispatcher FAILED OPEN with no resolvable atdd — the guard silently "
        "did not run (#1492)"
    )
    assert "cannot resolve" in result.stderr.lower()
    assert "pipx upgrade atdd" in result.stderr, "block message must name the repair"


def test_dispatcher_declares_no_bypass_env_var() -> None:
    """E030 retired the bypass-flag class; the dispatcher must not re-add one.

    E030's own guard greps for ATDD_SKIP_[A-Z_]+ specifically, so a differently
    named bypass would evade it on a technicality. This asserts the intent.
    """
    tpl = Path(ProjectInitializer(Path.cwd()).package_root) / "templates" / "hook-dispatcher.sh"
    body = tpl.read_text()
    offenders = [
        tok for tok in ("ATDD_SKIP", "ATDD_HOOK_DEGRADED", "ATDD_BYPASS", "ATDD_FORCE")
        if tok in body.replace("E030 retired that entire class", "")
    ]
    assert not offenders, f"dispatcher re-introduced a retired bypass class: {offenders}"


def test_every_declared_hook_is_installed(tmp_path: Path) -> None:
    """GT-002: every declared template gets an installed hook.

    6 of 11 were absent on main — including pre-commit-gh-issue-create.sh, the
    subject of consumer report #952 — because the installer skipped anything
    already present and nothing ever noticed the gap.

    Hermetic on purpose: it installs into tmp_path rather than judging the
    repo's own .atdd/hooks/. core.hooksPath is one shared file governing every
    worktree, so a validator that judged the live directory could only be made
    green by refreshing the whole fleet mid-flight.
    """
    initializer = ProjectInitializer(tmp_path)
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    initializer._install_hooks(force=False)

    installed = {
        p.name for p in (tmp_path / ".atdd" / "hooks").iterdir()
        if p.is_file() and not p.name.endswith(".local.bak")
    }
    missing = set(declared_hook_names()) - installed
    assert not missing, f"declared hooks were never installed: {sorted(missing)}"


def test_refresh_preserves_unrecognised_content_then_overwrites(tmp_path: Path) -> None:
    """A refresh always wins, but never destroys: unknown content → *.local.bak.

    Operator ruling on issue #1492 Decision #2. Skipping the update is the bug
    being fixed, so the refresh may not decline; the backup is what makes an
    unconditional overwrite non-destructive.
    """
    hooks_dir = tmp_path / ".atdd" / "hooks"
    hooks_dir.mkdir(parents=True)
    hand_edited = hooks_dir / "commit-msg"
    hand_edited.write_text("#!/bin/sh\n# operator's own guard\nexit 0\n")

    ProjectInitializer(tmp_path)._install_hooks(force=False)

    backup = hooks_dir / "commit-msg.local.bak"
    assert backup.is_file(), "hand-edited hook was destroyed without a backup"
    assert "operator's own guard" in backup.read_text()
    assert "ATDD managed hook dispatcher" in hand_edited.read_text(), (
        "refresh declined to update a hand-edited hook — that is the #1492 bug"
    )


def test_pristine_copy_is_replaced_without_a_backup(tmp_path: Path) -> None:
    """A pre-#1492 pristine copy is ours, so migration leaves no .bak litter.

    Every hook installed on the live fleet is byte-identical to its template
    (measured), so the migration to dispatchers should be silent for all of them.
    """
    hooks_dir = tmp_path / ".atdd" / "hooks"
    hooks_dir.mkdir(parents=True)
    pristine = hooks_dir / "commit-msg"
    pristine.write_text((packaged_hooks_dir() / "commit-msg").read_text())

    ProjectInitializer(tmp_path)._install_hooks(force=False)

    assert not (hooks_dir / "commit-msg.local.bak").exists(), (
        "a pristine pre-#1492 copy was needlessly backed up — every machine "
        "would get .bak litter on migration"
    )
    assert "ATDD managed hook dispatcher" in pristine.read_text()


def test_hooks_path_stdout_is_not_polluted_by_banners() -> None:
    """`atdd hooks path` stdout must be JUST the path.

    The dispatcher does `_HOOK_PATH=$(atdd hooks path ...)`. atdd prints an
    upgrade banner on some invocations; if that reached stdout the captured
    path would be garbage and every hook would block spuriously — enforcement
    that cries wolf, which is how #1442 taught operators to bypass guards.
    """
    from atdd.coach.commands.hooks import resolve_hook_path
    resolved = resolve_hook_path("commit-msg")
    assert resolved is not None and resolved.is_file()
    assert "\n" not in str(resolved), "resolved path must be a single line"


def test_every_packaged_hook_is_posix_sh() -> None:
    """The dispatcher execs via `sh`, which is only safe if every hook is sh.

    Guards the assumption rather than trusting it: a bash-only hook added later
    would be silently mis-executed.
    """
    offenders = {
        name: (packaged_hooks_dir() / name).read_text(errors="replace").splitlines()[0]
        for name in declared_hook_names()
        if (packaged_hooks_dir() / name).read_text(errors="replace").splitlines()[:1]
        and not (packaged_hooks_dir() / name).read_text(errors="replace").startswith("#!/bin/sh")
    }
    assert not offenders, (
        f"hooks are not #!/bin/sh, so `exec sh` would mis-run them: {offenders}"
    )
