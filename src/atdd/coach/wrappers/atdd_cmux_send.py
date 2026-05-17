# URN: component:spawn-agents:atdd-spawn-skeleton-and-harness:atdd-cmux-send:application
# Runtime: python
# Purpose: Pre-send classifier shim over `cmux send` that rejects raw `claude ...` launches (issue #662).

"""``atdd-cmux-send`` — a thin, semantic wrapper around the generic
``cmux send`` primitive.

Issue #662 — when an operator or agent hand-types
``cmux send <surface> "claude ..."`` instead of routing through
``atdd spawn``, the pane's incidental shell cwd (usually the workspace
root, NOT the issue worktree) silently binds the session. This shim
runs a pre-send classifier that:

* flags launch-intent ``claude`` payloads (``^claude``, ``claude\\n``,
  ``claude --``) and rejects them with exit 2 + an educational error
  pointing at ``atdd spawn --worktree``;
* passes non-launch payloads — including incidental ``claude`` mentions
  (``claude.json``, ``claude_code``, prose) — through to the real
  ``cmux send`` unchanged;
* honors a ``--i-know-what-im-doing`` escape flag so test scaffolding
  (and a knowing operator) can exercise the otherwise-rejected path.

Public contract:

* ``is_launch_intent(payload) -> bool`` — the pre-send classifier.
* ``main(argv, *, cmux_send=None) -> int`` — CLI entry. ``cmux_send`` is
  an injectable forwarder ``(surface, payload) -> int``; the real
  ``cmux send`` subprocess is used when ``None``. Positional argv is
  ``[<surface>, <payload>]``, optionally preceded by
  ``--i-know-what-im-doing``.
"""
from __future__ import annotations

import re
import subprocess
import sys
from typing import Callable, Optional, Sequence

# Rule-ID anchor — observers correlate raw-launch rejections on this.
SHIM_RULE_ID = "coach.spawn.reject-raw-cmux-claude"

_ESCAPE_FLAG = "--i-know-what-im-doing"

# Launch intent: after optional leading whitespace the payload's first
# token is exactly ``claude`` followed by whitespace or end-of-string.
# This flags ``^claude ``, ``claude\n`` and ``claude --`` without
# false-positiving on ``claudemon``, ``claude.json``, ``claude_code``,
# ``claude/config.yaml`` or an incidental ``claude`` later in the line.
_LAUNCH_INTENT_RE = re.compile(r"\s*claude(\s|$)")


def is_launch_intent(payload: str) -> bool:
    """Return True when ``payload`` is a raw Claude Code launch command."""
    return _LAUNCH_INTENT_RE.match(payload) is not None


def _educational_rejection(surface: str) -> str:
    """The exit-2 error body — names ``atdd spawn`` with a copy-pasteable command."""
    return (
        "❌ atdd-cmux-send: refusing to forward a raw `claude` launch "
        f"({SHIM_RULE_ID}).\n"
        "\n"
        "A raw `cmux send \"claude ...\"` binds the pane's incidental shell\n"
        "cwd (usually the workspace root, NOT the issue worktree). Route the\n"
        "launch through `atdd spawn`, which guarantees the worktree cwd:\n"
        "\n"
        "    atdd spawn --worktree <worktree> --issue <N> --from-prompt-file <prompt.md>\n"
        "\n"
        "If you genuinely need to bypass this guard (test scaffolding), re-run\n"
        f"with the escape flag:  atdd-cmux-send {_ESCAPE_FLAG} {surface} <payload>\n"
    )


def _real_cmux_send(surface: str, payload: str) -> int:
    """Forward ``(surface, payload)`` to the real ``cmux send`` binary."""
    completed = subprocess.run(["cmux", "send", surface, payload])
    return completed.returncode


def main(
    argv: Sequence[str],
    *,
    cmux_send: Optional[Callable[[str, str], int]] = None,
) -> int:
    """CLI entry point. Returns the process exit code.

    Exit 2 — the payload is launch intent and was rejected pre-send
    (the forwarder is never invoked), or argv is malformed.
    Otherwise the forwarder's return code is propagated.
    """
    args = list(argv)
    escape = False
    if args and args[0] == _ESCAPE_FLAG:
        escape = True
        args = args[1:]

    if len(args) < 2:
        print(
            f"❌ atdd-cmux-send: usage: atdd-cmux-send [{_ESCAPE_FLAG}] "
            "<surface> <payload>",
            file=sys.stderr,
        )
        return 2

    surface, payload = args[0], args[1]

    if not escape and is_launch_intent(payload):
        print(_educational_rejection(surface), file=sys.stderr)
        return 2

    forwarder = cmux_send if cmux_send is not None else _real_cmux_send
    return forwarder(surface, payload)


def console_main() -> int:
    """``[project.scripts]`` entry point — reads argv from ``sys.argv``."""
    return main(sys.argv[1:])


if __name__ == "__main__":  # pragma: no cover - exercised via console script
    sys.exit(console_main())
