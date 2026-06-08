"""Process + pidfile mechanism for the coach runtime (integration).

``ManagerRegistry`` persists one ``manager.json`` per workspace under a runtime
root, so `start` is idempotent across invocations and `stop`/`daemons` can find
exactly what was launched. ``SubprocessDaemonSpawner`` launches the existing
feed_daemon CLI detached (reuse — never a reimplementation). ``OsLivenessProbe``
and ``OsSignaller`` wrap ``os.kill``. ``build_feed_daemon_argv`` renders the
launch argv as a pure function.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from atdd.mediate_worker_decisions.coach_runtime.src.domain.managed_daemon import (
    ManagedDaemon,
)
from atdd.mediate_worker_decisions.coach_runtime.src.log import log as _log

_FEED_DAEMON_MODULE = (
    "atdd.mediate_worker_decisions.feed_daemon.src.presentation.feed_daemon_cli"
)

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")

# cmux env vars the detached daemon MUST keep to find cmux itself — the bundled
# CLI path. Everything else under the CMUX_ prefix is per-surface/panel/socket
# CLIENT-CONTEXT identity the daemon must NOT impersonate (#1007): inheriting the
# coach session's CMUX_PANEL_ID / empty CMUX_SOCKET / CMUX_SURFACE_ID / CMUX_AGENT_*
# made the daemon's ``cmux rpc`` break-pipe against the coach's dead surface.
_CMUX_ENV_KEEP = frozenset({"CMUX_BUNDLED_CLI_PATH"})


def scrub_cmux_client_context(env: dict) -> dict:
    """Return a copy of ``env`` with stale cmux CLIENT-CONTEXT vars removed.

    Drops every ``CMUX_*`` var except the bundled-CLI pointer cmux needs to find
    itself, so a detached daemon reaches the cmux server with a clean default
    socket instead of impersonating the coach session's dead surface/panel/socket
    (the #1007 broken-pipe root cause). Non-cmux vars (PATH, HOME, …) pass through.
    """
    return {
        key: value
        for key, value in env.items()
        if not key.startswith("CMUX_") or key in _CMUX_ENV_KEEP
    }


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
            pid=int(record["pid"]),
            lock_path=record.get("lock_path", ""),
            escalations_path=record.get("escalations_path", ""),
            verdicts_path=record.get("verdicts_path", ""),
        )
    except (KeyError, TypeError, ValueError) as exc:
        _log.debug("malformed manager record skipped", extra={"error": str(exc)})
        return None


class SubprocessDaemonSpawner:
    """Launch the feed_daemon CLI as a detached background process."""

    def __init__(self, python: Optional[str] = None) -> None:
        self._python = python or sys.executable

    def spawn(self, argv: List[str], *, log_path: Optional[str] = None) -> int:
        """Spawn the daemon detached, capturing its output to a durable log.

        stdout/stderr are wired to ``log_path`` (append, line-buffered) so a
        detached daemon's runtime failure — decide loop, LlmCoach, scope — leaves
        a diagnosable trace instead of vanishing into ``/dev/null`` (WMBT M004).
        stdin stays ``DEVNULL``. Without a ``log_path`` the output is discarded.

        The child's env has the stale cmux CLIENT-CONTEXT vars scrubbed (WMBT
        M005): a detached daemon that inherited the coach session's CMUX_PANEL_ID /
        empty CMUX_SOCKET / CMUX_SURFACE_ID / CMUX_AGENT_* would break-pipe on every
        ``cmux rpc`` against the coach's dead surface and silently see an empty Feed.
        """
        env = scrub_cmux_client_context(dict(os.environ))
        if log_path:
            log_file = Path(log_path)
            log_file.parent.mkdir(parents=True, exist_ok=True)
            # Append + line-buffered: a watched daemon's last line survives a crash.
            sink = open(log_file, "a", buffering=1, encoding="utf-8")
            try:
                proc = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=sink,
                    stderr=sink,
                    start_new_session=True,  # survive the parent shell exiting
                    env=env,
                )
            finally:
                # The child holds its own dup of the fd; the parent must not keep it.
                sink.close()
            return proc.pid
        proc = subprocess.Popen(  # pragma: no cover - discard path (no log sink)
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
        return proc.pid


class OsLivenessProbe:
    def is_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            _log.debug("pid not running", extra={"pid": pid})
            return False
        except PermissionError:
            _log.debug("pid alive but owned by another user", extra={"pid": pid})
            return True
        return True


class OsSignaller:
    def signal(self, pid: int, sig: int) -> None:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            _log.debug("pid already gone; signal is idempotent", extra={"pid": pid})
