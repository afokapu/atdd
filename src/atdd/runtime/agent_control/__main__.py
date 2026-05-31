"""Entry point for ``python -m atdd.runtime.agent_control`` — the pty-owning shim.

Usage (built by the spawn dispatch when cli-return is the transport, default):

  python -m atdd.runtime.agent_control --agent-id <id> --runtime-dir <path> \
      [--env KEY=VALUE ...] -- <adapter_command...>

The shim spawns <adapter_command> inside a pty it owns, tees output to
<runtime_dir>/agents/<id>/output.log, polls cli-return.jsonl, and writes
correction bytes (prompt + submit sentinel) to the adapter's pty stdin.

Extracted from ``atdd.coach.shim`` (Child 6, docs/coach-decomposition.md §13.6).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="atdd-agent-shim",
        description="Pty-owning shim that wraps an agent CLI process.",
    )
    p.add_argument("--agent-id", required=True, help="Runtime agent identifier.")
    p.add_argument(
        "--runtime-dir",
        required=True,
        type=Path,
        help="Root runtime directory (e.g. .atdd/runtime).",
    )
    p.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Set an environment variable in the spawned process (repeatable).",
    )
    p.add_argument(
        "adapter_command",
        nargs=argparse.REMAINDER,
        help="The adapter command to spawn (everything after --).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.runtime_dir = args.runtime_dir.resolve()

    # Strip leading '--' separator if present.
    cmd_tokens = args.adapter_command
    if cmd_tokens and cmd_tokens[0] == "--":
        cmd_tokens = cmd_tokens[1:]

    if not cmd_tokens:
        print("atdd-agent-shim: error: adapter command is required", file=sys.stderr)
        return 2

    env_overrides: dict[str, str] = {}
    for kv in args.env:
        k, _, v = kv.partition("=")
        if k:
            env_overrides[k] = v

    from atdd.runtime.agent_control._shim import PersonaShim

    shim = PersonaShim(
        agent_id=args.agent_id,
        spawn_command=cmd_tokens,
        runtime_dir=args.runtime_dir,
        env_overrides=env_overrides,
    )
    return shim.run()


if __name__ == "__main__":
    sys.exit(main())
