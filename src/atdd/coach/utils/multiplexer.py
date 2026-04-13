"""
Multiplexer abstraction — unified interface over cmux (preferred) and tmux.

Used by `atdd orchestrate` to launch parallel agent sessions, and by
`atdd babysit` to read screens and send input.

Convention: src/atdd/coach/conventions/orchestration.convention.yaml
SPEC IDs: SPEC-COACH-ORCH-0003

Operations (unified):
    new_workspace(cwd, command, name=None) -> workspace_ref
    read_screen(workspace_ref, lines=50)   -> str
    send(workspace_ref, text)              -> None
    send_key(workspace_ref, key)           -> None
    list_workspaces()                      -> list[str]
    close(workspace_ref)                   -> None

Auto-detection:
    get_multiplexer()  # cmux if `cmux --version` succeeds, else tmux, else None.
"""
from __future__ import annotations

import shutil
import subprocess
from abc import ABC, abstractmethod
from typing import Optional


class MultiplexerError(RuntimeError):
    """Raised when a multiplexer operation fails."""


class MultiplexerBackend(ABC):
    """Abstract backend contract for cmux/tmux."""

    name: str = "abstract"

    @abstractmethod
    def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> str:
        """Create a workspace and return an opaque reference."""

    @abstractmethod
    def read_screen(self, workspace_ref: str, lines: int = 50) -> str:
        """Capture the last `lines` lines of the workspace screen."""

    @abstractmethod
    def send(self, workspace_ref: str, text: str) -> None:
        """Send literal text to the workspace."""

    @abstractmethod
    def send_key(self, workspace_ref: str, key: str) -> None:
        """Send a key press (e.g. 'Enter', 'C-c') to the workspace."""

    @abstractmethod
    def list_workspaces(self) -> list[str]:
        """List all known workspace references."""

    @abstractmethod
    def close(self, workspace_ref: str) -> None:
        """Close/kill the workspace."""


def _run(cmd: list[str], capture: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            check=True,
            capture_output=capture,
            text=True,
        )
    except FileNotFoundError as exc:
        raise MultiplexerError(f"binary not found: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise MultiplexerError(
            f"{' '.join(cmd)} failed (exit {exc.returncode}): "
            f"{(exc.stderr or '').strip()}"
        ) from exc


class CmuxBackend(MultiplexerBackend):
    """cmux backend — workspace-based abstraction."""

    name = "cmux"

    def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> str:
        cmd = ["cmux", "new-workspace", "--cwd", cwd, "--command", command]
        if name:
            cmd.extend(["--name", name])
        result = _run(cmd)
        ref = (result.stdout or "").strip().splitlines()[-1] if result.stdout else ""
        if not ref:
            ref = name or cwd
        return ref

    def read_screen(self, workspace_ref: str, lines: int = 50) -> str:
        result = _run([
            "cmux", "read-screen",
            "--workspace", workspace_ref,
            "--lines", str(lines),
        ])
        return result.stdout or ""

    def send(self, workspace_ref: str, text: str) -> None:
        _run(["cmux", "send", "--workspace", workspace_ref, text], capture=False)

    def send_key(self, workspace_ref: str, key: str) -> None:
        _run(["cmux", "send-key", "--workspace", workspace_ref, key], capture=False)

    def list_workspaces(self) -> list[str]:
        result = _run(["cmux", "list-workspaces"])
        return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]

    def close(self, workspace_ref: str) -> None:
        _run(["cmux", "close-workspace", "--workspace", workspace_ref], capture=False)


class TmuxBackend(MultiplexerBackend):
    """tmux backend — pane-based fallback.

    workspace_ref is a tmux target like "session:window.pane".
    """

    name = "tmux"

    def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> str:
        session = name or f"atdd-{abs(hash(cwd)) % 10000}"
        _run([
            "tmux", "new-session", "-d", "-s", session, "-c", cwd, command,
        ], capture=False)
        return session

    def read_screen(self, workspace_ref: str, lines: int = 50) -> str:
        result = _run([
            "tmux", "capture-pane", "-t", workspace_ref, "-p", "-S", f"-{lines}",
        ])
        return result.stdout or ""

    def send(self, workspace_ref: str, text: str) -> None:
        _run(["tmux", "send-keys", "-t", workspace_ref, text], capture=False)

    def send_key(self, workspace_ref: str, key: str) -> None:
        _run(["tmux", "send-keys", "-t", workspace_ref, key], capture=False)

    def list_workspaces(self) -> list[str]:
        result = _run(["tmux", "list-sessions", "-F", "#{session_name}"])
        return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]

    def close(self, workspace_ref: str) -> None:
        _run(["tmux", "kill-session", "-t", workspace_ref], capture=False)


def detect_multiplexer() -> Optional[str]:
    """Return 'cmux', 'tmux', or None based on which binary is on PATH and runnable."""
    for binary in ("cmux", "tmux"):
        if shutil.which(binary) is None:
            continue
        try:
            subprocess.run(
                [binary, "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            continue
        return binary
    return None


def get_multiplexer(preferred: Optional[str] = None) -> MultiplexerBackend:
    """Return a backend instance. Honors `preferred` then falls back to detection."""
    choice = preferred or detect_multiplexer()
    if choice == "cmux":
        return CmuxBackend()
    if choice == "tmux":
        return TmuxBackend()
    raise MultiplexerError(
        "No multiplexer available — install cmux (preferred) or tmux."
    )
