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

import json
import os
import re
import shutil
import sys
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

    def new_surface_in_pane(
        self,
        pane_ref: MultiplexerRef,
        cwd: Optional[str] = None,
        command: Optional[str] = None,
        name: Optional[str] = None,
    ) -> MultiplexerRef:
        """Create a surface inside an existing pane (tab co-location).

        Unlike new_surface, this never allocates a new pane — it attaches
        to the pane identified by pane_ref. Used to place the observer tab
        alongside the persona tab inside the same grid cell (#658).
        """
        raise NotImplementedError(
            f"{self.name} backend does not support new_surface_in_pane"
        )

    def surface_to_pane(self, surface_ref: MultiplexerRef) -> MultiplexerRef:
        """Return the pane ref that owns surface_ref.

        Used to resolve the persona's pane before attaching the observer
        tab to the same pane (#658).
        """
        raise NotImplementedError(
            f"{self.name} backend does not support surface_to_pane"
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

    def paste_text(self, ref: MultiplexerRef, text: str) -> None:
        """Paste multi-line text as a single input block.

        Unlike ``send``, embedded newlines must stay literal and NOT
        submit. This is required to inject a multi-line launch prompt
        into an interactive TUI (e.g. Claude Code) — a plain per-line
        ``send`` would submit the input box on the first newline.
        Callers issue a separate ``send_key(ref, "Enter")`` to submit
        once the full block has landed.

        Default falls back to ``send`` (which does NOT preserve the
        no-submit semantic). Every concrete backend that drives a real
        terminal — cmux, tmux, zellij — overrides this with its native
        bracketed-paste primitive. The fallback exists only so partial
        test doubles need not implement it.
        """
        self.send(ref, text)

    @abstractmethod
    def list_workspaces(self) -> list[str]:
        """List all known workspace references."""

    @abstractmethod
    def close(self, ref: MultiplexerRef) -> None:
        """Close/kill the workspace or surface."""

    def new_persona_surface(
        self,
        cwd: str,
        command: str,
        name: str,
        observer_runtime_root: str,
        observer_agent_id: str,
        observer_name: str,
        observer_command: str,
    ) -> MultiplexerRef:
        """Create persona surface + co-spawn observer surface.

        Default: calls new_surface twice (persona, then observer).
        Observer failure emits a structured JSON event to stderr but does NOT
        raise — persona spawn must succeed even if observer fails.
        Backends that support a dedicated tab-in-pane primitive can override.
        """
        import json
        import sys

        persona_ref = self.new_surface(cwd=cwd, command=command, name=name)
        try:
            self.new_surface(cwd=cwd, command=observer_command, name=observer_name)
        except Exception as exc:
            print(
                json.dumps({
                    "event": "observer_cospawn_failed",
                    "persona_name": name,
                    "observer_name": observer_name,
                    "observer_agent_id": observer_agent_id,
                    "error": str(exc),
                }),
                file=sys.stderr,
            )
        return persona_ref

    def rename(self, ref: MultiplexerRef, name: str) -> None:
        """Rename a workspace or surface to ``name``.

        Default implementation is a no-op so backends without a rename
        primitive (zellij, tmux) silently degrade instead of breaking
        the orchestrate flow. Issue #470 — canonical session naming.
        Override in cmux backend.
        """
        del ref, name


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


def _extract_ref_token(stdout: str, prefix: str) -> str:
    """Extract the first ``<prefix>:<N>`` token from a cmux OK-line.

    cmux mutating commands (``new-pane``, ``new-split``, ``new-surface``) emit
    a single line of the shape ``OK <ref> [<ref>...]`` where each ref is
    ``<kind>:<integer>``. The CLI only accepts the bare ``<kind>:<integer>``
    token as a handle — feeding back the whole OK-line is rejected with
    "Invalid pane handle". Returns ``""`` when no matching token is present;
    callers raise ``MultiplexerError`` so the failure surfaces clearly.
    """
    pattern = re.compile(rf"(?:^|\s){re.escape(prefix)}:(\d+)\b")
    for line in (stdout or "").splitlines():
        match = pattern.search(line)
        if match:
            return f"{prefix}:{match.group(1)}"
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
        ref = _extract_ref_token(result.stdout or "", "workspace")
        if not ref:
            raise MultiplexerError(
                f"cmux new-workspace returned no workspace ref: "
                f"{(result.stdout or '').strip()!r}"
            )
        return ref

    def new_surface(
        self,
        workspace_ref: Optional[MultiplexerRef] = None,
        pane_ref: Optional[MultiplexerRef] = None,
        cwd: Optional[str] = None,
        command: Optional[str] = None,
        name: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> MultiplexerRef:
        # Bug #5 fix (#697): `cmux new-pane` ALWAYS creates a default "Terminal"
        # surface. Previously this code ignored it and added another surface,
        # leaving 1 unused surface per spawn. Now: when creating a new pane,
        # reuse its auto-default surface (rename + seed) instead of adding
        # another. When given an existing pane_ref, add a tab as before.
        creating_new_pane = pane_ref is None
        if creating_new_pane:
            new_pane_cmd = ["cmux", "new-pane"]
            if workspace_ref:
                new_pane_cmd.extend(["--workspace", workspace_ref])
            if direction:
                # Issue #470: right-anchored grid layout. cmux new-pane accepts
                # --direction {right,left,up,down}; default behavior is preserved
                # when callers don't pass it.
                new_pane_cmd.extend(["--direction", direction])
            pane_result = _run(new_pane_cmd)
            pane_ref = _extract_ref_token(pane_result.stdout or "", "pane")
            if not pane_ref:
                raise MultiplexerError(
                    f"cmux new-pane returned no pane ref: {(pane_result.stdout or '').strip()!r}"
                )
            # Reuse the auto-default surface that `cmux new-pane` creates.
            surfaces_result = _run(["cmux", "list-pane-surfaces", "--pane", pane_ref])
            surface_ref = _extract_ref_token(surfaces_result.stdout or "", "surface")
            if not surface_ref:
                raise MultiplexerError(
                    f"cmux new-pane: no default surface found in {pane_ref}: "
                    f"{(surfaces_result.stdout or '').strip()!r}"
                )
            if name:
                # Rename the default surface to the desired name.
                _run(
                    ["cmux", "rename-tab", "--surface", surface_ref, name],
                    capture=False,
                )
        else:
            # Existing pane: add a new surface as a tab.
            new_surface_cmd = ["cmux", "new-surface", "--pane", pane_ref]
            if name:
                new_surface_cmd.extend(["--name", name])
            surface_result = _run(new_surface_cmd)
            surface_ref = _extract_ref_token(surface_result.stdout or "", "surface")
            if not surface_ref:
                raise MultiplexerError(
                    f"cmux new-surface returned no surface ref: {(surface_result.stdout or '').strip()!r}"
                )

        if cwd or command:
            seed_parts = []
            if cwd:
                seed_parts.append(f"cd {cwd}")
            if command:
                seed_parts.append(command)
            seed_text = " && ".join(seed_parts) + "\n"
            _run(
                ["cmux", "send", "--surface", surface_ref, seed_text],
                capture=False,
            )

        return surface_ref

    def new_surface_in_pane(
        self,
        pane_ref: MultiplexerRef,
        cwd: Optional[str] = None,
        command: Optional[str] = None,
        name: Optional[str] = None,
    ) -> MultiplexerRef:
        new_surface_cmd = ["cmux", "new-surface", "--pane", pane_ref]
        if name:
            new_surface_cmd.extend(["--name", name])
        surface_result = _run(new_surface_cmd)
        surface_ref = _extract_ref_token(surface_result.stdout or "", "surface")
        if not surface_ref:
            raise MultiplexerError(
                f"cmux new-surface returned no surface ref: {(surface_result.stdout or '').strip()!r}"
            )
        if cwd or command:
            seed_parts = []
            if cwd:
                seed_parts.append(f"cd {cwd}")
            if command:
                seed_parts.append(command)
            seed_text = " && ".join(seed_parts) + "\n"
            _run(
                ["cmux", "send", "--surface", surface_ref, seed_text],
                capture=False,
            )
        return surface_ref

    def surface_to_pane(self, surface_ref: MultiplexerRef) -> MultiplexerRef:
        # Iterate `cmux list-panes` and find the pane whose `list-pane-surfaces`
        # output contains the target surface. O(N) for N panes — fine for
        # typical workspace sizes (<10).
        #
        # Why not `cmux describe-surface`? It doesn't exist.
        # Why not `cmux rpc surface.read_text '{"surface":"..."}'`? Upstream cmux
        # bug: the rpc ignores the surface param and returns whatever surface is
        # focused in the operator's view (verified 2026-05-15).
        panes_result = _run(["cmux", "list-panes"])
        pane_pattern = re.compile(r"\bpane:(\d+)\b")
        for match in pane_pattern.finditer(panes_result.stdout or ""):
            pane_ref = f"pane:{match.group(1)}"
            surfaces_result = _run(
                ["cmux", "list-pane-surfaces", "--pane", pane_ref]
            )
            if surface_ref in (surfaces_result.stdout or ""):
                return pane_ref
        raise MultiplexerError(
            f"surface_to_pane: could not find pane containing {surface_ref}"
        )

    def read_screen(self, ref: MultiplexerRef, lines: int = 50) -> str:
        if _is_surface_ref(ref):
            result = _run([
                "cmux", "read-screen",
                "--surface", ref,
                "--lines", str(lines),
            ])
            return result.stdout or ""
        result = _run([
            "cmux", "read-screen",
            "--workspace", ref,
            "--lines", str(lines),
        ])
        return result.stdout or ""

    def send(self, ref: MultiplexerRef, text: str) -> None:
        if _is_surface_ref(ref):
            _run(
                ["cmux", "send", "--surface", ref, text],
                capture=False,
            )
            return
        _run(["cmux", "send", "--workspace", ref, text], capture=False)

    def send_key(self, ref: MultiplexerRef, key: str) -> None:
        # `cmux rpc surface.send_key` takes JSON params, not CLI flags. Use the
        # regular `cmux send-key --surface <ref> <key>` CLI for both ref kinds
        # (verified at runtime 2026-05-15).
        if _is_surface_ref(ref):
            _run(["cmux", "send-key", "--surface", ref, key], capture=False)
            return
        _run(["cmux", "send-key", "--workspace", ref, key], capture=False)

    def paste_text(self, ref: MultiplexerRef, text: str) -> None:
        # Stage the text in the cmux buffer, then bracketed-paste it into the
        # surface so multi-line content lands as one input block (newlines
        # stay literal, no premature submit). Verified end-to-end 2026-05-15
        # against Claude Code v2.1.142.
        _run(["cmux", "set-buffer", text], capture=False)
        if _is_surface_ref(ref):
            _run(["cmux", "paste-buffer", "--surface", ref], capture=False)
            return
        _run(["cmux", "paste-buffer", "--workspace", ref], capture=False)

    def list_workspaces(self) -> list[str]:
        result = _run(["cmux", "list-workspaces"])
        return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]

    def close(self, ref: MultiplexerRef) -> None:
        if _is_surface_ref(ref):
            _run(["cmux", "close-surface", "--surface", ref], capture=False)
            return
        _run(["cmux", "close-workspace", "--workspace", ref], capture=False)

    def rename(self, ref: MultiplexerRef, name: str) -> None:
        """Rename a cmux surface/workspace tab title (issue #470).

        Best-effort: failures degrade silently so a missing/renamed cmux
        rename verb does not crash orchestrate. Babysit will retry on
        the next tick.
        """
        if not name:
            return
        try:
            if _is_surface_ref(ref):
                _run(
                    ["cmux", "rename-tab", "--surface", ref, name],
                    capture=False,
                )
            else:
                _run(
                    ["cmux", "rename-workspace", "--workspace", ref, name],
                    capture=False,
                )
        except MultiplexerError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            # Best-effort: cmux build may not expose rename verbs; the
            # validator is advisory and babysit retries every tick.
            pass

    def new_persona_surface(
        self,
        cwd: str,
        command: str,
        name: str,
        observer_runtime_root: str,
        observer_agent_id: str,
        observer_name: str,
        observer_command: str,
    ) -> MultiplexerRef:
        """Cmux-native co-spawn: persona surface + observer as TAB in same pane.

        Override of MultiplexerBackend default (which would create two separate
        panes). Persona spawn must succeed even if observer co-spawn fails.
        Both surfaces are renamed canonically so the link is visible in
        cmux tab list (sort-adjacent + ``:obs`` suffix).
        """
        persona_ref = self.new_surface(cwd=cwd, command=command, name=name)
        self.rename(persona_ref, name)
        try:
            pane_ref = self.surface_to_pane(persona_ref)
            observer_ref = self.new_surface_in_pane(
                pane_ref=pane_ref,
                cwd=cwd,
                command=observer_command,
                name=observer_name,
            )
            self.rename(observer_ref, observer_name)
        except Exception as exc:
            print(
                json.dumps({
                    "event": "observer_cospawn_failed",
                    "persona_name": name,
                    "observer_name": observer_name,
                    "observer_agent_id": observer_agent_id,
                    "error": str(exc),
                }),
                file=sys.stderr,
            )
        return persona_ref


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

    def paste_text(self, workspace_ref: str, text: str) -> None:
        # tmux set-buffer stages the text; paste-buffer -p uses bracketed
        # paste so a multi-line TUI input box receives it as one block.
        # -d deletes the buffer after pasting to avoid buffer-stack growth.
        _run(["tmux", "set-buffer", text], capture=False)
        _run(
            ["tmux", "paste-buffer", "-d", "-p", "-t", workspace_ref],
            capture=False,
        )

    def list_workspaces(self) -> list[str]:
        result = _run(["tmux", "list-sessions", "-F", "#{session_name}"])
        return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]

    def close(self, workspace_ref: str) -> None:
        _run(["tmux", "kill-session", "-t", workspace_ref], capture=False)

    def rename(self, ref: MultiplexerRef, name: str) -> None:
        """Rename a tmux window. Best-effort.

        `tmux rename-window -t <ref> <name>` retitles the window containing
        ref. If ref is "session" form, renames the active window in that
        session. If ref is "session:window" form, renames that specific window.
        """
        if not name:
            return
        try:
            _run(
                ["tmux", "rename-window", "-t", ref, name],
                capture=False,
            )
        except MultiplexerError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            # Best-effort: rename failures don't crash spawn flow.
            pass

    def new_persona_surface(
        self,
        cwd: str,
        command: str,
        name: str,
        observer_runtime_root: str,
        observer_agent_id: str,
        observer_name: str,
        observer_command: str,
    ) -> MultiplexerRef:
        """Tmux-native co-spawn: persona session + observer as SECOND PANE.

        Override of MultiplexerBackend default. tmux's "tab in pane" equivalent
        is "split-window" — two panes side-by-side in the same window. The
        operator cycles between persona and observer via Ctrl-b o.

        Both window names get the canonical ``:obs`` link via rename-window
        (observer pane title via select-pane -T).
        """
        persona_ref = self.new_workspace(cwd=cwd, command=command, name=name)
        self.rename(persona_ref, name)
        try:
            # Split window: observer as new pane on the right.
            _run(
                ["tmux", "split-window", "-h", "-t", persona_ref, "-c", cwd, observer_command],
                capture=False,
            )
            # Title the observer pane (tmux pane titles via select-pane -T).
            _run(
                ["tmux", "select-pane", "-t", persona_ref, "-T", observer_name],
                capture=False,
            )
        except Exception as exc:
            print(
                json.dumps({
                    "event": "observer_cospawn_failed",
                    "persona_name": name,
                    "observer_name": observer_name,
                    "observer_agent_id": observer_agent_id,
                    "error": str(exc),
                }),
                file=sys.stderr,
            )
        return persona_ref


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

    def paste_text(self, workspace_ref: str, text: str) -> None:
        # zellij has no buffer/paste-buffer primitive; `action write-chars`
        # writes literal characters (newlines included) without submitting,
        # which is exactly the bracketed-paste semantic paste_text needs.
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

    def list_workspaces(self) -> list[str]:
        result = _run(["zellij", "list-sessions", "-s", "-n"])
        return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]

    def close(self, workspace_ref: str) -> None:
        _run(["zellij", "delete-session", "--force", workspace_ref], capture=False)

    def rename(self, ref: MultiplexerRef, name: str) -> None:
        """Rename the active zellij tab in the given session. Best-effort.

        Targets the session via ZELLIJ_SESSION_NAME env var (per zellij action
        targeting convention). Renames whichever tab is currently active in
        that session.
        """
        if not name:
            return
        env = {**os.environ, "ZELLIJ_SESSION_NAME": ref}
        try:
            subprocess.run(
                ["zellij", "action", "rename-tab", name],
                check=True, env=env, capture_output=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            # Best-effort: rename failures don't crash spawn flow.
            pass

    def new_persona_surface(
        self,
        cwd: str,
        command: str,
        name: str,
        observer_runtime_root: str,
        observer_agent_id: str,
        observer_name: str,
        observer_command: str,
    ) -> MultiplexerRef:
        """Zellij-native co-spawn: persona session + observer as SECOND PANE.

        Override of MultiplexerBackend default. zellij's "tab in pane"
        equivalent is "new-pane in current tab" — two panes side-by-side in the
        same tab. The operator cycles between panes via Alt-arrows.

        The tab name gets the canonical persona name (zellij rename-tab).
        Observer pane title is set if the zellij build supports pane naming.
        """
        persona_ref = self.new_workspace(cwd=cwd, command=command, name=name)
        self.rename(persona_ref, name)
        try:
            env = {**os.environ, "ZELLIJ_SESSION_NAME": persona_ref}
            # new-pane in current tab, split right; runs observer_command.
            # `--` separates zellij args from the command to run.
            shell_invocation = ["bash", "-c", f"cd {cwd} && {observer_command}"]
            subprocess.run(
                ["zellij", "action", "new-pane", "--direction", "right", "--"] + shell_invocation,
                check=True, env=env, capture_output=True,
            )
        except Exception as exc:
            print(
                json.dumps({
                    "event": "observer_cospawn_failed",
                    "persona_name": name,
                    "observer_name": observer_name,
                    "observer_agent_id": observer_agent_id,
                    "error": str(exc),
                }),
                file=sys.stderr,
            )
        return persona_ref


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


class FakeMultiplexer(MultiplexerBackend):
    """In-memory test double for MultiplexerBackend.

    Records spawn calls so integration tests can assert the
    phase→persona sequence without requiring a real cmux daemon.
    Inject via constructor into ColdStartDriver or monkeypatch the
    spawn module's _resolve_multiplexer in tests (per R1, issue #645).
    """

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._surface_pane: dict[str, str] = {}
        self.new_persona_surface_calls: list[dict] = []

    def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> MultiplexerRef:
        ref = f"workspace:{len(self.calls) + 1}"
        self.calls.append({"op": "new_workspace", "cwd": cwd, "command": command, "name": name, "ref": ref})
        return ref

    def new_surface(
        self,
        workspace_ref: Optional[MultiplexerRef] = None,
        pane_ref: Optional[MultiplexerRef] = None,
        cwd: Optional[str] = None,
        command: Optional[str] = None,
        name: Optional[str] = None,
    ) -> MultiplexerRef:
        surface_ref = f"surface:{len(self.calls) + 1}"
        resolved_pane = pane_ref if pane_ref is not None else f"pane:{len(self.calls)}"
        self._surface_pane[surface_ref] = resolved_pane
        self.calls.append({"op": "new_surface", "pane_ref": resolved_pane, "cwd": cwd, "command": command, "name": name, "ref": surface_ref})
        return surface_ref

    def new_surface_in_pane(
        self,
        pane_ref: MultiplexerRef,
        cwd: Optional[str] = None,
        command: Optional[str] = None,
        name: Optional[str] = None,
    ) -> MultiplexerRef:
        surface_ref = f"surface:{len(self.calls) + 1}"
        self._surface_pane[surface_ref] = pane_ref
        self.calls.append({"op": "new_surface_in_pane", "pane_ref": pane_ref, "cwd": cwd, "command": command, "name": name, "ref": surface_ref})
        return surface_ref

    def surface_to_pane(self, surface_ref: MultiplexerRef) -> MultiplexerRef:
        return self._surface_pane[surface_ref]

    def read_screen(self, ref: MultiplexerRef, lines: int = 50) -> str:
        return ""

    def send(self, ref: MultiplexerRef, text: str) -> None:
        self.calls.append({"op": "send", "ref": ref, "text": text})

    def send_key(self, ref: MultiplexerRef, key: str) -> None:
        self.calls.append({"op": "send_key", "ref": ref, "key": key})

    def paste_text(self, ref: MultiplexerRef, text: str) -> None:
        self.calls.append({"op": "paste_text", "ref": ref, "text": text})

    def list_workspaces(self) -> list[str]:
        return [c["ref"] for c in self.calls if c.get("op") in ("new_workspace",)]

    def close(self, ref: MultiplexerRef) -> None:
        self.calls.append({"op": "close", "ref": ref})

    def new_persona_surface(
        self,
        cwd: str,
        command: str,
        name: str,
        observer_runtime_root: str,
        observer_agent_id: str,
        observer_name: str,
        observer_command: str,
    ) -> MultiplexerRef:
        persona_ref = self.new_surface(cwd=cwd, command=command, name=name)
        observer_ref = self.new_surface(cwd=cwd, command=observer_command, name=observer_name)
        self.new_persona_surface_calls.append({
            "persona_ref": persona_ref,
            "observer_ref": observer_ref,
            "persona_name": name,
            "observer_name": observer_name,
            "observer_agent_id": observer_agent_id,
        })
        return persona_ref

    def rename(self, ref: MultiplexerRef, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})
