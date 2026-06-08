"""cmux-surface launch + manager-registry mechanism for the coach runtime.

``ManagerRegistry`` persists one ``manager.json`` per watched workspace under a
runtime root, so `start` is idempotent and `stop`/`daemons` can find exactly what
was launched. ``CmuxSurfaceDaemonLauncher`` launches the existing feed_daemon CLI
INSIDE a headless cmux surface (``cmux new-workspace --focus false --command``) —
the #1007 fix: cmux rejects orphaned/detached processes (every ``cmux rpc`` from a
``subprocess.Popen(start_new_session=True)`` daemon broken-pipes), but a process
running inside a cmux surface has socket access. ``CmuxWorkspaceLiveness`` reads
liveness from the daemon's surface still existing; ``CmuxWorkspaceCloser`` closes
it. ``build_feed_daemon_argv`` renders the launch argv as a pure function.
"""
from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path
from typing import Callable, List, Optional

from atdd.mediate_worker_decisions.commons.cmux_cli import run_cmux, strip_ansi
from atdd.mediate_worker_decisions.coach_runtime.src.domain.managed_daemon import (
    ManagedDaemon,
)
from atdd.mediate_worker_decisions.coach_runtime.src.log import log as _log

_FEED_DAEMON_MODULE = (
    "atdd.mediate_worker_decisions.feed_daemon.src.presentation.feed_daemon_cli"
)

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_WORKSPACE_REF = re.compile(r"workspace:\d+")


def workspace_slug(workspace_id: str) -> str:
    """A filesystem-safe directory name for a (possibly uuid/slash) workspace id."""
    slug = _SAFE.sub("-", workspace_id.strip()).strip("-")
    return slug or "default"


def build_feed_daemon_argv(
    *,
    python: str,
    workspace_id: str,
    lock_path: str,
    escalations_path: str,
    verdicts_path: str,
) -> List[str]:
    """Render the argv that launches the workspace-scoped feed_daemon CLI.

    Reuses the existing feed_daemon CLI wholesale via ``python -m`` — the daemon
    brain (decide/escalate/dedup/ledgers) is never reimplemented here.
    """
    return [
        python,
        "-m",
        _FEED_DAEMON_MODULE,
        "--workspace",
        workspace_id,
        "--lock",
        lock_path,
        "--escalations",
        escalations_path,
        "--verdicts",
        verdicts_path,
    ]


class ManagerRegistry:
    """File-backed per-workspace registry of coach-managed daemons."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def _dir(self, workspace_id: str) -> Path:
        return self._root / workspace_slug(workspace_id)

    def _file(self, workspace_id: str) -> Path:
        return self._dir(workspace_id) / "manager.json"

    def save(self, daemon: ManagedDaemon) -> None:
        target = self._file(daemon.workspace_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(daemon.to_record()), encoding="utf-8")
        os.replace(tmp, target)  # atomic publish

    def load(self, workspace_id: str) -> Optional[ManagedDaemon]:
        target = self._file(workspace_id)
        if not target.exists():
            return None
        try:
            record = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            _log.debug(
                "manager pidfile unreadable; treating as absent",
                extra={"path": str(target), "error": str(exc)},
            )
            return None
        return _daemon_from_record(record)

    def load_all(self) -> List[ManagedDaemon]:
        if not self._root.exists():
            return []
        out: List[ManagedDaemon] = []
        for child in sorted(self._root.iterdir()):
            manifest = child / "manager.json"
            if not manifest.exists():
                continue
            try:
                record = json.loads(manifest.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                _log.debug(
                    "manager pidfile unreadable; skipping",
                    extra={"path": str(manifest), "error": str(exc)},
                )
                continue
            daemon = _daemon_from_record(record)
            if daemon is not None:
                out.append(daemon)
        return out

    def remove(self, workspace_id: str) -> None:
        target = self._file(workspace_id)
        try:
            target.unlink()
        except FileNotFoundError:
            _log.debug(
                "manager pidfile already absent; remove is idempotent",
                extra={"workspace_id": workspace_id},
            )


def _daemon_from_record(record: dict) -> Optional[ManagedDaemon]:
    try:
        return ManagedDaemon(
            workspace_id=record["workspace_id"],
            daemon_workspace=record["daemon_workspace"],
            lock_path=record.get("lock_path", ""),
            escalations_path=record.get("escalations_path", ""),
            verdicts_path=record.get("verdicts_path", ""),
        )
    except (KeyError, TypeError, ValueError) as exc:
        _log.debug("malformed manager record skipped", extra={"error": str(exc)})
        return None


def _daemon_command(argv: List[str], log_path: Optional[str]) -> str:
    """Render the daemon argv as a shell command for ``--command`` (typed into the
    surface's shell), redirecting stdout+stderr to the durable daemon.log so a
    runtime failure leaves a diagnosable trace (WMBT M004 / #1008)."""
    cmd = shlex.join(argv)
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        cmd = f"{cmd} >> {shlex.quote(log_path)} 2>&1"
    return cmd


class CmuxSurfaceDaemonLauncher:
    """Launch the feed_daemon CLI INSIDE a headless cmux surface.

    cmux rejects orphaned/detached processes — a ``subprocess.Popen`` daemon
    (#1007) broken-pipes on every ``cmux rpc``. Launching it as a ``cmux
    new-workspace --focus false --command`` surface makes it a socket-recognized
    process. Returns the daemon's OWN cmux workspace ref.
    """

    def __init__(
        self, *, cwd: str, runner: Callable[..., str] = run_cmux
    ) -> None:
        self._cwd = cwd
        self._run = runner

    def spawn(
        self, argv: List[str], *, name: str, log_path: Optional[str] = None
    ) -> str:
        command = _daemon_command(argv, log_path)
        out = strip_ansi(
            self._run(
                "new-workspace",
                "--name",
                name,
                "--cwd",
                self._cwd,
                "--focus",
                "false",
                "--command",
                command,
            )
        )
        match = _WORKSPACE_REF.search(out)
        if match is None:
            raise RuntimeError(
                f"cmux new-workspace did not return a workspace ref (got: {out!r})"
            )
        return match.group(0)


class CmuxWorkspaceLiveness:
    """Liveness = the daemon's cmux surface workspace still exists."""

    def __init__(self, runner: Callable[..., str] = run_cmux) -> None:
        self._run = runner

    def is_alive(self, daemon_workspace: str) -> bool:
        if not daemon_workspace:
            return False
        out = strip_ansi(self._run("list-workspaces"))
        return daemon_workspace in set(_WORKSPACE_REF.findall(out))


class CmuxWorkspaceCloser:
    """Stop the daemon by closing its cmux surface workspace (idempotent)."""

    def __init__(self, runner: Callable[..., str] = run_cmux) -> None:
        self._run = runner

    def close(self, daemon_workspace: str) -> None:
        if not daemon_workspace:
            return
        try:
            self._run("close-workspace", "--workspace", daemon_workspace)
        except Exception as exc:  # already gone / unreachable — close is idempotent
            _log.debug(
                "close-workspace failed; treating as idempotent",
                extra={"daemon_workspace": daemon_workspace, "error": str(exc)},
            )
