"""Multiplexer primer — print a one-screen cheat-sheet on first dispatch.

Detects CMUX_WORKSPACE_ID, TMUX, or ZELLIJ_SESSION_NAME in the environment
and prints the per-backend primer once per session (marker-gated).
A ``--multiplexer-help`` CLI flag prints the primer and exits 0.

Issue #812 / E005.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Dict, IO, Optional

_PRIMER_TEXT: Dict[str, str] = {
    "cmux": """\
┌─ Multiplexer quick reference (cmux) ─────────────────────────────────────────┐
│  cmux tree                              # list all workspaces and surfaces    │
│  cmux send-key <surface> <key>          # send a keystroke to a surface       │
│  cmux read-screen <surface>             # capture current pane text           │
│  cmux close-surface <surface>           # close a surface (remove pane/tab)   │
│  cmux paste-buffer <surface> --text … # paste text into a surface            │
│                                                                                │
│  Tip: cmux send-key <surface> Enter     # submit a queued prompt              │
└────────────────────────────────────────────────────────────────────────────────┘
""",
    "tmux": """\
┌─ Multiplexer quick reference (tmux) ─────────────────────────────────────────┐
│  tmux list-panes -a                     # list all panes                      │
│  tmux send-keys -t <target> <key>       # send a keystroke                    │
│  tmux capture-pane -t <target> -p       # capture pane text                   │
│  tmux kill-pane -t <target>             # close a pane                        │
│  tmux load-buffer - ; paste-buffer -t … # paste text                          │
└────────────────────────────────────────────────────────────────────────────────┘
""",
    "zellij": """\
┌─ Multiplexer quick reference (zellij) ────────────────────────────────────────┐
│  zellij action list-clients             # list sessions                        │
│  zellij run --                          # run a command in a new pane          │
│  zellij action close-pane               # close focused pane                   │
│  zellij action write-chars '…'          # write text to focused pane           │
└────────────────────────────────────────────────────────────────────────────────┘
""",
}

_BACKEND_FROM_ENV = {
    "CMUX_WORKSPACE_ID": "cmux",
    "TMUX": "tmux",
    "ZELLIJ_SESSION_NAME": "zellij",
}


class MultiplexerPrimer:
    """Gate-and-print the multiplexer primer once per session."""

    MARKER_NAME = "primer_shown"

    def _detect_backend(self, env: dict) -> Optional[str]:
        for var, backend in _BACKEND_FROM_ENV.items():
            if env.get(var):
                return backend
        return None

    def _marker_path(self, marker_dir: Path) -> Path:
        return marker_dir / self.MARKER_NAME

    def should_print(self, env: dict, marker_dir: Path) -> bool:
        """Return True when a multiplexer is detected and the primer has not yet been printed."""
        if not self._detect_backend(env):
            return False
        return not self._marker_path(marker_dir).exists()

    def print_primer(
        self,
        backend: str,
        out: IO[str],
        marker_dir: Path,
    ) -> None:
        """Print the backend-appropriate primer to *out* and write the marker file."""
        text = _PRIMER_TEXT.get(backend, _PRIMER_TEXT["cmux"])
        out.write(text)
        marker_dir.mkdir(parents=True, exist_ok=True)
        self._marker_path(marker_dir).touch()

    def maybe_print(self, env: dict, marker_dir: Path, out: Optional[IO[str]] = None) -> None:
        """Print primer if should_print returns True; no-op otherwise."""
        if not self.should_print(env=env, marker_dir=marker_dir):
            return
        backend = self._detect_backend(env) or "cmux"
        self.print_primer(backend=backend, out=out or sys.stdout, marker_dir=marker_dir)
