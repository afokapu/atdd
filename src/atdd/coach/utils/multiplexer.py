"""
Multiplexer abstraction — unified interface over cmux (preferred), zellij, and tmux.

Used by `atdd orchestrate` to launch parallel agent sessions, and by
`atdd babysit` to read screens and send input.

Convention: src/atdd/coach/conventions/orchestration.convention.yaml
SPEC IDs: SPEC-COACH-ORCH-0003

Refs come in two flavours and are dispatched by string prefix:
    workspace:NN  → top-level cmux workspace
    surface:NN    → terminal tab inside a pane inside a workspace

Operations (unified — all ref-consumers accept either workspace or surface refs):
    new_workspace(cwd, command, name=None)                          -> MultiplexerRef
    new_surface(workspace_ref?, pane_ref?, cwd?, command?, name?)   -> MultiplexerRef
    read_screen(ref, lines=50)                                      -> str
    send(ref, text)                                                 -> None
    send_key(ref, key)                                              -> None
    list_workspaces()                                               -> list[str]
    close(ref)                                                      -> None

Auto-detection precedence:
    get_multiplexer()  # cmux > zellij > tmux > None.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from typing import Optional


# Type alias — opaque ref string with prefix `workspace:` or `surface:`.
MultiplexerRef = str


class MultiplexerError(RuntimeError):
    """Raised when a multiplexer operation fails."""


class MultiplexerBackend(ABC):
    """Abstract backend contract for cmux/zellij/tmux."""

    name: str = "abstract"

    @abstractmethod
    def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> MultiplexerRef:
        """Create a workspace and return an opaque reference."""

    def new_surface(
        self,
        workspace_ref: Optional[MultiplexerRef] = None,
        pane_ref: Optional[MultiplexerRef] = None,
        cwd: Optional[str] = None,
        command: Optional[str] = None,
        name: Optional[str] = None,
    ) -> MultiplexerRef:
        """Create a surface (terminal tab) inside a pane and return its ref.

        Backends without pane semantics raise NotImplementedError.
        """
        raise NotImplementedError(
            f"{self.name} backend does not support pane/surface creation"
        )

    @abstractmethod
    def read_screen(self, ref: MultiplexerRef, lines: int = 50) -> str:
        """Capture the last `lines` lines of the workspace or surface screen."""

    @abstractmethod
    def send(self, ref: MultiplexerRef, text: str) -> None:
        """Send literal text to the workspace or surface."""

    @abstractmethod
    def send_key(self, ref: MultiplexerRef, key: str) -> None:
        """Send a key press (e.g. 'Enter', 'C-c') to the workspace or surface."""

    @abstractmethod
    def list_workspaces(self) -> list[str]:
        """List all known workspace references."""

    @abstractmethod
    def close(self, ref: MultiplexerRef) -> None:
        """Close/kill the workspace or surface."""


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


def _is_surface_ref(ref: str) -> bool:
    return ref.startswith("surface:")


def _last_nonempty_line(stdout: str) -> str:
    for line in reversed((stdout or "").splitlines()):
        s = line.strip()
        if s:
            return s
    return ""


class CmuxBackend(MultiplexerBackend):
    """cmux backend — workspace + pane/surface dispatch.

    Ref prefix dispatch table:
        workspace:NN  → cmux <verb> --workspace NN
        surface:NN    → cmux rpc surface.<verb>  (cmux close-surface for close)
    """

    name = "cmux"

    def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> MultiplexerRef:
        cmd = ["cmux", "new-workspace", "--cwd", cwd, "--command", command]
        if name:
            cmd.extend(["--name", name])
        result = _run(cmd)
        ref = _last_nonempty_line(result.stdout or "")
        if not ref:
            ref = name or cwd
        return ref

    def new_surface(
        self,
        workspace_ref: Optional[MultiplexerRef] = None,
        pane_ref: Optional[MultiplexerRef] = None,
        cwd: Optional[str] = None,
        command: Optional[str] = None,
        name: Optional[str] = None,
    ) -> MultiplexerRef:
        if pane_ref is None:
            new_pane_cmd = ["cmux", "new-pane"]
            if workspace_ref:
                new_pane_cmd.extend(["--workspace", workspace_ref])
            pane_result = _run(new_pane_cmd)
            pane_ref = _last_nonempty_line(pane_result.stdout or "")
            if not pane_ref:
                raise MultiplexerError("cmux new-pane returned no pane ref")

        new_surface_cmd = ["cmux", "new-surface", "--pane", pane_ref]
        if name:
            new_surface_cmd.extend(["--name", name])
        surface_result = _run(new_surface_cmd)
        surface_ref = _last_nonempty_line(surface_result.stdout or "")
        if not surface_ref:
            raise MultiplexerError("cmux new-surface returned no surface ref")

        if cwd or command:
            seed_parts = []
            if cwd:
                seed_parts.append(f"cd {cwd}")
            if command:
                seed_parts.append(command)
            seed_text = " && ".join(seed_parts) + "\n"
            _run(
                ["cmux", "rpc", "surface.send_text", "--surface", surface_ref, seed_text],
                capture=False,
            )

        return surface_ref

    def read_screen(self, ref: MultiplexerRef, lines: int = 50) -> str:
        if _is_surface_ref(ref):
            result = _run(["cmux", "rpc", "surface.read_text", "--surface", ref])
            out = result.stdout or ""
            if lines and lines > 0:
                tail = out.splitlines()[-lines:]
                return "\n".join(tail) + ("\n" if out.endswith("\n") else "")
            return out
        result = _run([
            "cmux", "read-screen",
            "--workspace", ref,
            "--lines", str(lines),
        ])
        return result.stdout or ""

    def send(self, ref: MultiplexerRef, text: str) -> None:
        if _is_surface_ref(ref):
            _run(
                ["cmux", "rpc", "surface.send_text", "--surface", ref, text],
                capture=False,
            )
            return
        _run(["cmux", "send", "--workspace", ref, text], capture=False)

    def send_key(self, ref: MultiplexerRef, key: str) -> None:
        if _is_surface_ref(ref):
            _run(
                ["cmux", "rpc", "surface.send_key", "--surface", ref, key],
                capture=False,
            )
            return
        _run(["cmux", "send-key", "--workspace", ref, key], capture=False)

    def list_workspaces(self) -> list[str]:
        result = _run(["cmux", "list-workspaces"])
        return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]

    def close(self, ref: MultiplexerRef) -> None:
        if _is_surface_ref(ref):
            _run(["cmux", "close-surface", "--surface", ref], capture=False)
            return
        _run(["cmux", "close-workspace", "--workspace", ref], capture=False)


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


class ZellijBackend(MultiplexerBackend):
    """zellij backend — session-based workspace abstraction.

    workspace_ref is a zellij session name. Sessions are created detached via
    `zellij attach --create-background`, so the orchestrator does not need a TTY.
    Action commands (read_screen/send/send_key) target a specific session via
    the ZELLIJ_SESSION_NAME environment variable, since `zellij action` does
    not accept a `--session` flag.
    """

    name = "zellij"

    def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> str:
        session = name or f"atdd-{abs(hash(cwd)) % 10000}"
        _run([
            "zellij", "attach", "--create-background", session,
            "options", "--default-cwd", cwd,
        ], capture=False)
        if command:
            self.send(session, command)
            self.send_key(session, "Enter")
        return session

    def read_screen(self, workspace_ref: str, lines: int = 50) -> str:
        cmd = ["zellij", "action", "dump-screen", "--full"]
        env = {**os.environ, "ZELLIJ_SESSION_NAME": workspace_ref}
        try:
            result = subprocess.run(
                cmd, check=True, capture_output=True, text=True, env=env,
            )
        except FileNotFoundError as exc:
            raise MultiplexerError("binary not found: zellij") from exc
        except subprocess.CalledProcessError as exc:
            raise MultiplexerError(
                f"{' '.join(cmd)} failed (exit {exc.returncode}): "
                f"{(exc.stderr or '').strip()}"
            ) from exc
        out = result.stdout or ""
        if lines and lines > 0:
            tail = out.splitlines()[-lines:]
            return "\n".join(tail) + ("\n" if out.endswith("\n") else "")
        return out

    def send(self, workspace_ref: str, text: str) -> None:
        cmd = ["zellij", "action", "write-chars", text]
        env = {**os.environ, "ZELLIJ_SESSION_NAME": workspace_ref}
        try:
            subprocess.run(cmd, check=True, env=env)
        except FileNotFoundError as exc:
            raise MultiplexerError("binary not found: zellij") from exc
        except subprocess.CalledProcessError as exc:
            raise MultiplexerError(
                f"{' '.join(cmd)} failed (exit {exc.returncode})"
            ) from exc

    def send_key(self, workspace_ref: str, key: str) -> None:
        cmd = ["zellij", "action", "send-keys", key]
        env = {**os.environ, "ZELLIJ_SESSION_NAME": workspace_ref}
        try:
            subprocess.run(cmd, check=True, env=env)
        except FileNotFoundError as exc:
            raise MultiplexerError("binary not found: zellij") from exc
        except subprocess.CalledProcessError as exc:
            raise MultiplexerError(
                f"{' '.join(cmd)} failed (exit {exc.returncode})"
            ) from exc

    def list_workspaces(self) -> list[str]:
        result = _run(["zellij", "list-sessions", "-s", "-n"])
        return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]

    def close(self, workspace_ref: str) -> None:
        _run(["zellij", "delete-session", "--force", workspace_ref], capture=False)


def detect_multiplexer() -> Optional[str]:
    """Return 'cmux', 'zellij', 'tmux', or None based on which binary is on PATH and runnable.

    Precedence (cmux > zellij > tmux) reflects backend fitness:
    cmux's workspace model is the design target; zellij has native detached
    sessions and per-session targeting; tmux is the ubiquitous fallback.
    """
    for binary in ("cmux", "zellij", "tmux"):
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
    if choice == "zellij":
        return ZellijBackend()
    if choice == "tmux":
        return TmuxBackend()
    raise MultiplexerError(
        "No multiplexer available — install cmux (preferred), zellij, or tmux."
    )
