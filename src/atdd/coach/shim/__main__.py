"""Entry point for `python -m atdd.coach.shim` and the `atdd-shim` CLI script.

Usage (invoked by cmd_spawn when ATDD_CORRECTION_TRANSPORT=cli-return):

  atdd-shim --agent-id <id> --runtime-dir <path> [--env KEY=VALUE ...] -- <adapter_command...>

The shim spawns <adapter_command> inside a pty it owns, tees output to
<runtime_dir>/agents/<id>/output.log, polls cli-return.jsonl, and writes
correction bytes to the adapter's pty stdin.
"""
from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="atdd-shim",
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
        help="Set an environment variable in the spawned process (repeatable). "
        "Shape A fix (#854): env vars are passed via this flag rather than as "
        "shell-style KEY=value argv prefixes which fail without shell=True.",
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

    # Strip leading '--' separator if present.
    cmd_tokens = args.adapter_command
    if cmd_tokens and cmd_tokens[0] == "--":
        cmd_tokens = cmd_tokens[1:]

    if not cmd_tokens:
        print("atdd-shim: error: adapter command is required", file=sys.stderr)
        return 2

    # Parse --env KEY=VALUE flags into a dict.
    env_overrides: dict[str, str] = {}
    for kv in args.env:
        k, _, v = kv.partition("=")
        if k:
            env_overrides[k] = v

    from atdd.coach.shim.persona_shim import PersonaShim

    shim = PersonaShim(
        agent_id=args.agent_id,
        spawn_command=cmd_tokens,
        runtime_dir=args.runtime_dir,
        env_overrides=env_overrides,
    )
    return shim.run()


if __name__ == "__main__":
    sys.exit(main())
