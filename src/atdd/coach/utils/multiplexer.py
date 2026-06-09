"""
Multiplexer abstraction — unified interface over cmux (preferred), zellij, and tmux.

Used by `atdd coach` to launch parallel agent sessions, and by the observer
to read screens and send corrections.

Convention: src/atdd/coach/conventions/session.convention.yaml::multiplexer

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

# #1025: consume the workspace-handle sanitizer through the
# enforce-surface-conformance feature's application surface (not the domain
# directly), so the domain is consumed within its own feature's layers
# (SPEC-CODER-COMP-0003). The surface imports only the pure domain function, so
# this top-level import carries no composition/integration weight (no cycle).
from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.presentation.workspace_handle_surface import (
    sanitize_cmux_workspace_handle,
)


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

    def resolve_focused_pane(
        self, workspace: Optional[MultiplexerRef] = None
    ) -> MultiplexerRef:
        """Return the currently-focused pane ref for surface-mode spawning.

        Used by _create_surface('surface') to pick the canonical spawn
        target without calling the deprecated new-pane RPC (issue #830).
        """
        raise NotImplementedError(
            f"{self.name} backend does not support resolve_focused_pane"
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

    def respawn_pane(
        self, ref: MultiplexerRef, command: Optional[str] = None
    ) -> None:
        """Relaunch the process in an existing surface/pane (issue #730).

        Kills the current process in ``ref`` and starts a fresh one running
        ``command`` — a new process, NOT a conversation reset. The coach uses
        this to swap the persona agent in place on each phase transition while
        keeping the issue's single persistent surface.

        Backends without respawn support raise NotImplementedError; callers
        treat that as 'leave the surface as-is'.
        """
        raise NotImplementedError(
            f"{self.name} backend does not support respawn_pane"
        )

    @abstractmethod
    def list_workspaces(self) -> list[str]:
        """List all known workspace references."""

    @abstractmethod
    def close(self, ref: MultiplexerRef, workspace: Optional[MultiplexerRef] = None) -> None:
        """Close/kill the workspace or surface.

        ``workspace`` scopes a surface ref to its workspace — cmux resolves
        short ``surface:`` refs against the selected workspace only (#655).
        """

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
        the coach launch flow. Issue #470 — canonical session naming.
        Override in cmux backend.
        """
        del ref, name

    def capture_pane_text(self, surface_ref: MultiplexerRef) -> str:
        """Capture the current visible text content of a surface pane.

        Returns the full visible text of the pane with ANSI escape sequences
        stripped, suitable for substring-matching against expected TUI markers
        (e.g. "⏺ Thinking", "paste again to expand", canonical session name).

        E011 (#799): Every spawn pipeline stage calls this after firing its
        cmux command to verify the expected post-condition. The base class
        raises NotImplementedError; concrete backends (CmuxBackend) implement
        via ``cmux capture-pane``. Test doubles override with scripted responses.
        """
        raise NotImplementedError(
            f"{self.name} backend does not support capture_pane_text"
        )


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


def _ws_flag(workspace: Optional[str]) -> list[str]:
    """`["--workspace", <ref>]` when a workspace is known, else `[]`.

    cmux resolves short ``surface:``/``pane:`` refs against the *selected*
    workspace only, so every ref-bearing cmux call must carry --workspace
    to resolve reliably (#655). Splat into an argv: ``[..., *_ws_flag(ws)]``.
    """
    return ["--workspace", workspace] if workspace else []


def _target_args(ref: str, workspace: Optional[str] = None) -> list[str]:
    """cmux argv fragment targeting ``ref``.

    A ``surface:`` ref needs ``--surface`` plus ``--workspace`` to resolve
    (#655); a ``workspace:`` ref is itself the ``--workspace`` value.
    """
    if _is_surface_ref(ref):
        return ["--surface", ref, *_ws_flag(workspace)]
    return ["--workspace", ref]


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
        # Workspace that owns the created surface. EVERY ref-bearing cmux call
        # must be scoped to it: cmux resolves short `surface:`/`pane:` refs
        # against the *selected* workspace only, so an unscoped call silently
        # hits the wrong surface or fails outright (#655 SMOKE).
        resolved_workspace = workspace_ref

        if creating_new_pane:
            new_pane_cmd = ["cmux", "new-pane", *_ws_flag(workspace_ref)]
            if direction:
                # Issue #470: right-anchored grid layout. cmux new-pane accepts
                # --direction {right,left,up,down}; default behavior is preserved
                # when callers don't pass it.
                new_pane_cmd.extend(["--direction", direction])
            pane_stdout = _run(new_pane_cmd).stdout or ""
            # `cmux new-pane` echoes `OK surface:N pane:M workspace:K` — every
            # ref we need is already here. Reuse that default surface directly
            # instead of a `cmux list-pane-surfaces --pane` round-trip: that
            # call needs --workspace, and when it failed it stranded the
            # just-created pane outside the transactional guard (#655 bug 4).
            pane_ref = _extract_ref_token(pane_stdout, "pane")
            surface_ref = _extract_ref_token(pane_stdout, "surface")
            if not resolved_workspace:
                resolved_workspace = _extract_ref_token(pane_stdout, "workspace") or None
            if not pane_ref or not surface_ref:
                raise MultiplexerError(
                    f"cmux new-pane returned an incomplete ref set "
                    f"(need surface + pane): {pane_stdout.strip()!r}"
                )
        else:
            # Existing pane: add a new surface as a tab.
            new_surface_cmd = ["cmux", "new-surface", "--pane", pane_ref,
                               *_ws_flag(workspace_ref)]
            if name:
                new_surface_cmd.extend(["--name", name])
            surface_result = _run(new_surface_cmd)
            surface_ref = _extract_ref_token(surface_result.stdout or "", "surface")
            if not surface_ref:
                raise MultiplexerError(
                    f"cmux new-surface returned no surface ref: {(surface_result.stdout or '').strip()!r}"
                )

        # Transactional spawn (#655): the pane/surface now exists. ANY later
        # step that fails must close it so the failed attempt leaves no orphan
        # pane — every ref-bearing call below is scoped with --workspace.
        try:
            if creating_new_pane and name:
                # Rename the default surface to the desired name.
                _run(
                    ["cmux", "rename-tab", "--surface", surface_ref,
                     *_ws_flag(resolved_workspace), name],
                    capture=False,
                )
            if cwd or command:
                seed_parts = []
                if cwd:
                    seed_parts.append(f"cd {cwd}")
                if command:
                    seed_parts.append(command)
                seed_text = " && ".join(seed_parts) + "\n"
                _run(
                    ["cmux", "send", "--surface", surface_ref,
                     *_ws_flag(resolved_workspace), seed_text],
                    capture=False,
                )
        except Exception:
            self._close_quietly(surface_ref, workspace=resolved_workspace)
            raise

        return surface_ref

    def new_surface_in_pane(
        self,
        pane_ref: MultiplexerRef,
        cwd: Optional[str] = None,
        command: Optional[str] = None,
        name: Optional[str] = None,
        workspace: Optional[MultiplexerRef] = None,
    ) -> MultiplexerRef:
        new_surface_cmd = ["cmux", "new-surface", "--pane", pane_ref,
                           *_ws_flag(workspace)]
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
                ["cmux", "send", "--surface", surface_ref,
                 *_ws_flag(workspace), seed_text],
                capture=False,
            )
        return surface_ref

    def resolve_focused_pane(
        self, workspace: Optional[MultiplexerRef] = None
    ) -> MultiplexerRef:
        # Parse `cmux list-panes` to find the currently-focused pane.
        # Output format: "* pane:4  [N surfaces]  [focused]"
        # Returns the first pane ref found — the focused pane in a typical
        # single-pane workspace is always the only entry.
        result = _run(["cmux", "list-panes", *_ws_flag(workspace)])
        pane_pattern = re.compile(r"\bpane:(\d+)\b")
        for match in pane_pattern.finditer(result.stdout or ""):
            return f"pane:{match.group(1)}"
        raise MultiplexerError(
            f"cmux list-panes returned no pane refs "
            f"(workspace={workspace!r}): {(result.stdout or '').strip()!r}"
        )

    def surface_to_pane(
        self, surface_ref: MultiplexerRef, workspace: Optional[MultiplexerRef] = None
    ) -> MultiplexerRef:
        # Iterate `cmux list-panes` and find the pane whose `list-pane-surfaces`
        # output contains the target surface. O(N) for N panes — fine for
        # typical workspace sizes (<10).
        #
        # Both calls are scoped with --workspace: cmux resolves short `pane:`
        # refs against the *selected* workspace only (#655).
        #
        # Why not `cmux describe-surface`? It doesn't exist.
        # Why not `cmux rpc surface.read_text '{"surface":"..."}'`? Upstream cmux
        # bug: the rpc ignores the surface param and returns whatever surface is
        # focused in the operator's view (verified 2026-05-15).
        panes_result = _run(["cmux", "list-panes", *_ws_flag(workspace)])
        pane_pattern = re.compile(r"\bpane:(\d+)\b")
        for match in pane_pattern.finditer(panes_result.stdout or ""):
            pane_ref = f"pane:{match.group(1)}"
            surfaces_result = _run(
                ["cmux", "list-pane-surfaces", "--pane", pane_ref, *_ws_flag(workspace)]
            )
            if surface_ref in (surfaces_result.stdout or ""):
                return pane_ref
        raise MultiplexerError(
            f"surface_to_pane: could not find pane containing {surface_ref}"
        )

    def read_screen(
        self,
        ref: MultiplexerRef,
        lines: int = 50,
        workspace: Optional[MultiplexerRef] = None,
    ) -> str:
        cmd = ["cmux", "read-screen", *_target_args(ref, workspace),
               "--lines", str(lines)]
        return _run(cmd).stdout or ""

    def send(
        self, ref: MultiplexerRef, text: str, workspace: Optional[MultiplexerRef] = None
    ) -> None:
        _run(["cmux", "send", *_target_args(ref, workspace), text], capture=False)

    def send_key(
        self, ref: MultiplexerRef, key: str, workspace: Optional[MultiplexerRef] = None
    ) -> None:
        # `cmux rpc surface.send_key` takes JSON params, not CLI flags. Use the
        # regular `cmux send-key --surface <ref> <key>` CLI for both ref kinds
        # (verified at runtime 2026-05-15).
        _run(["cmux", "send-key", *_target_args(ref, workspace), key], capture=False)

    def paste_text(
        self, ref: MultiplexerRef, text: str, workspace: Optional[MultiplexerRef] = None
    ) -> None:
        # Stage the text in the cmux buffer, then bracketed-paste it into the
        # surface so multi-line content lands as one input block (newlines
        # stay literal, no premature submit). Verified end-to-end 2026-05-15
        # against Claude Code v2.1.142.
        _run(["cmux", "set-buffer", text], capture=False)
        _run(["cmux", "paste-buffer", *_target_args(ref, workspace)], capture=False)

    def list_workspaces(self) -> list[str]:
        # cmux decorates each line with a current-workspace marker (`* `), a
        # trailing title, and `[selected]`; sanitize to the bare `workspace:N`
        # token so a downstream `cmux list-panes --workspace <handle>` never
        # receives decoration (the #1025 "Invalid workspace handle" crash). The
        # sanitizer is consumed through the enforce-surface-conformance feature's
        # application surface (imported at module top), not the domain directly.
        result = _run(["cmux", "list-workspaces"])
        handles: list[str] = []
        for line in (result.stdout or "").splitlines():
            if not line.strip():
                continue
            try:
                handles.append(sanitize_cmux_workspace_handle(line))
            except ValueError:
                # A header/blank/non-workspace line carries no handle — skip it
                # rather than flow a bad handle into a workspace-scoped cmux call.
                continue
        return handles

    def _surface_workspace(self, surface_ref: str) -> Optional[str]:
        """Resolve which workspace owns ``surface_ref`` via ``cmux tree --all``.

        cmux resolves a short ``surface:`` ref against the *selected* workspace
        only — so a ref-bearing call to a surface in any other workspace must
        carry ``--workspace`` to resolve (#655). cmux exposes no direct
        surface→workspace query, so the owning workspace is read off the
        surface tree. Returns ``None`` when the surface is not found (caller
        falls back to the unscoped, selected-workspace behaviour).
        """
        out = ""
        try:
            out = _run(["cmux", "tree", "--all"]).stdout or ""
        except MultiplexerError as exc:
            # Best-effort: a failed tree read just means the respawn falls back
            # to the unscoped (selected-workspace) path — warn, do not abort.
            # The empty ``out`` then yields ``None`` via the loop below.
            print(
                f"⚠️  cmux tree read failed, respawn will not be "
                f"workspace-scoped: {exc}",
                file=sys.stderr,
            )
        current_ws: Optional[str] = None
        ws_re = re.compile(r"\bworkspace (workspace:\d+)\b")
        surf_re = re.compile(rf"\bsurface {re.escape(surface_ref)}\b")
        for line in out.splitlines():
            ws_match = ws_re.search(line)
            if ws_match:
                current_ws = ws_match.group(1)
            if surf_re.search(line):
                return current_ws
        return None

    def respawn_pane(
        self, ref: MultiplexerRef, command: Optional[str] = None
    ) -> None:
        """Relaunch the process in an existing cmux surface (issue #730, #746).

        Swaps the persona agent in place — kills the current process and
        starts a fresh one — so the issue keeps its single persistent surface
        across phase transitions.

        The respawn is scoped with ``--workspace`` (issue #746): cmux resolves
        a short ``surface:`` ref only against the *selected* workspace, so an
        unscoped respawn of a surface in any other workspace fails with
        "Surface is not a terminal" — exactly the coach's multi-issue case,
        where each issue owns its own workspace.
        """
        workspace = self._surface_workspace(ref) if _is_surface_ref(ref) else None
        cmd = ["cmux", "respawn-pane", *_target_args(ref, workspace)]
        if command:
            cmd.extend(["--command", command])
        _run(cmd, capture=False)

    def close(self, ref: MultiplexerRef, workspace: Optional[MultiplexerRef] = None) -> None:
        if _is_surface_ref(ref):
            # cmux resolves a short `surface:` ref against the *selected*
            # workspace only — pass --workspace so the ref resolves no matter
            # which workspace is focused (#655).
            _run(
                ["cmux", "close-surface", "--surface", ref, *_ws_flag(workspace)],
                capture=False,
            )
            return
        _run(["cmux", "close-workspace", "--workspace", ref], capture=False)

    def _close_quietly(
        self, ref: MultiplexerRef, workspace: Optional[MultiplexerRef] = None
    ) -> None:
        """Close a half-created surface during spawn-failure cleanup (#655).

        Never raises: orphan-pane cleanup must not mask the original spawn
        error that triggered it.
        """
        try:
            self.close(ref, workspace=workspace)
        except MultiplexerError as exc:
            print(
                f"⚠️  orphan-pane cleanup could not close {ref}: {exc}",
                file=sys.stderr,
            )

    def rename(
        self, ref: MultiplexerRef, name: str, workspace: Optional[MultiplexerRef] = None
    ) -> None:
        """Rename a cmux surface/workspace tab title (issue #470).

        Best-effort: failures degrade silently so a missing/renamed cmux
        rename verb does not crash the coach launch. The observer will retry
        on the next tick. ``workspace`` scopes a surface ref (#655).
        """
        if not name:
            return
        try:
            if _is_surface_ref(ref):
                _run(
                    ["cmux", "rename-tab", "--surface", ref,
                     *_ws_flag(workspace), name],
                    capture=False,
                )
            else:
                _run(
                    ["cmux", "rename-workspace", "--workspace", ref, name],
                    capture=False,
                )
        except MultiplexerError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            # Best-effort: cmux build may not expose rename verbs; the
            # validator is advisory and the observer retries every tick.
            pass

    def capture_pane_text(self, surface_ref: MultiplexerRef) -> str:
        """Capture visible pane text from a cmux surface (E011, issue #799).

        Runs ``cmux capture-pane --surface <ref>`` and returns the output with
        ANSI escape sequences stripped. Used by _verify_stage to poll for
        expected post-condition signals (thinking markers, paste indicators,
        canonical name suffix) without blocking.

        Returns empty string on any failure so callers retry on next poll
        rather than raising prematurely.
        """
        import re as _re

        try:
            result = _run(["cmux", "capture-pane", "--surface", surface_ref])
            raw = result.stdout or ""
            # Strip ANSI escape sequences (ESC [ ... m and ESC [ ... control codes).
            ansi_escape = _re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b[@-Z\\-_]")
            return ansi_escape.sub("", raw)
        except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-01
            return ""

    # ------------------------------------------------------------------
    # Layout geometry over per-workspace surfaces (issue #865)
    # ------------------------------------------------------------------
    def reorder_workspace_after(
        self, workspace_id: str, anchor_workspace_id: str
    ) -> None:
        """Position ``workspace_id`` immediately right of ``anchor_workspace_id``
        within its window (``cmux reorder-workspace --after``).

        A workspace-ordering op: the worker stays its OWN workspace (and its own
        daemon scope), so the never-collapse invariant holds by construction.
        """
        _run(
            [
                "cmux", "reorder-workspace",
                "--workspace", workspace_id,
                "--after", anchor_workspace_id,
            ],
            capture=False,
        )

    def current_workspace(self) -> MultiplexerRef:
        """Return the operator's currently-selected workspace ref."""
        out = (_run(["cmux", "current-workspace"]).stdout or "").strip()
        token = _extract_ref_token(out, "workspace")
        return token or out

    def surface_workspace(self, surface_ref: MultiplexerRef) -> MultiplexerRef:
        """Resolve the workspace that owns ``surface_ref``.

        Cross-references ``surface.list`` (surface → pane) against each
        workspace's ``list-panes`` (pane → workspace).
        """
        payload = json.loads(_run(["cmux", "rpc", "surface.list"]).stdout or "{}")
        pane_id = ""
        for surface in payload.get("surfaces", []):
            if surface.get("ref") == surface_ref:
                pane_id = surface.get("pane_id") or ""
                break
        if not pane_id:
            raise MultiplexerError(
                f"surface {surface_ref!r} not found in cmux surface.list"
            )
        for ws in self.list_workspaces():
            if pane_id in self._pane_uuids(ws):
                return ws
        raise MultiplexerError(
            f"could not resolve owning workspace for {surface_ref!r}"
        )

    @staticmethod
    def _pane_uuids(workspace_id: str) -> set[str]:
        """Global pane UUIDs in ``workspace_id`` (short ``pane:N`` refs resolve
        per selected-workspace, so UUIDs are the reliable cross-workspace key)."""
        out = _run(
            ["cmux", "list-panes", *_ws_flag(workspace_id), "--id-format", "uuids"]
        ).stdout or ""
        return set(re.findall(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f-]{27}", out))

    def list_surface_identities(self, workspace_id: str) -> list[str]:
        """Return the distinct surface identities resident in ``workspace_id``.

        Uses ``list-pane-surfaces --id-format uuids`` — the reliable
        cross-workspace primitive: ``surface.list`` (with resume_binding
        checkpoints) only reports the *selected* workspace, whereas this resolves
        any workspace. Surface UUIDs are globally unique, so a worker that kept its
        own single-identity workspace yields exactly one identity disjoint from
        every other worker's (the never-collapse proof, #865/#1013). A
        single-worker workspace yields exactly one.
        """
        out = _run(
            [
                "cmux", "list-pane-surfaces",
                *_ws_flag(workspace_id), "--id-format", "uuids",
            ]
        ).stdout or ""
        identities: list[str] = []
        for uuid in re.findall(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f-]{27}", out):
            if uuid not in identities:
                identities.append(uuid)
        return identities

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

    def respawn_pane(
        self, ref: MultiplexerRef, command: Optional[str] = None
    ) -> None:
        """Relaunch the process in an existing tmux pane (issue #746).

        ``tmux respawn-pane -k`` kills the pane's current process and starts a
        fresh one in the SAME pane — a new process, not a conversation reset —
        so the issue keeps its single persistent surface across phase
        transitions.
        """
        cmd = ["tmux", "respawn-pane", "-k", "-t", ref]
        if command:
            cmd.append(command)
        _run(cmd, capture=False)


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

    def respawn_pane(
        self, ref: MultiplexerRef, command: Optional[str] = None
    ) -> None:
        """Relaunch the process in an existing zellij session (issue #746).

        zellij has no single respawn verb — ``close-pane`` kills the focused
        pane's process and ``new-pane`` opens a fresh one. Both target the SAME
        session (via ``ZELLIJ_SESSION_NAME``), so the session — the issue's
        persistent surface — is kept across phase transitions.
        """
        env = {**os.environ, "ZELLIJ_SESSION_NAME": ref}
        try:
            subprocess.run(
                ["zellij", "action", "close-pane"],
                check=True, env=env, capture_output=True,
            )
            if command:
                subprocess.run(
                    ["zellij", "action", "new-pane", "--",
                     "bash", "-c", command],
                    check=True, env=env, capture_output=True,
                )
        except FileNotFoundError as exc:
            raise MultiplexerError("binary not found: zellij") from exc
        except subprocess.CalledProcessError as exc:
            raise MultiplexerError(
                f"zellij respawn-pane failed (exit {exc.returncode})"
            ) from exc


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
        self._focused_pane: str = "pane:1"

    def resolve_focused_pane(self, workspace: Optional[MultiplexerRef] = None) -> MultiplexerRef:
        return self._focused_pane

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

    def capture_pane_text(self, surface_ref: MultiplexerRef) -> str:
        """Return the next scripted pane capture from ``_pane_captures``, or empty.

        Tests script responses by setting ``mux._pane_captures = [...]`` before
        calling code that polls capture_pane_text. Each call pops the front;
        the empty string is returned once the list is exhausted.
        """
        captures: list[str] = getattr(self, "_pane_captures", [])
        if captures:
            return captures.pop(0)
        return ""
