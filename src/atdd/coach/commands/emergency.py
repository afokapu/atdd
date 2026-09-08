"""`atdd emergency` — structured single-use emergency bypass for hook gates.

E031 (2026-05-26): After E030 retired all ATDD_SKIP_* env-var bypass flags,
this command provides the ONLY sanctioned bypass path for genuine emergencies.

Usage::

    atdd emergency --reason "infra validator outage; fix tracked in #999"

Effect:
  - Creates .atdd/EMERGENCY_BYPASS with a timestamp and the reason string.
  - Appends a JSON audit record to .atdd/emergency-audit.jsonl.
  - The bypass is valid for 5 minutes (hooks check file mtime).
  - After 5 minutes the file is ignored; run the command again if needed.

The bypass file is NOT deleted automatically by hooks — remove it manually
once the emergency is resolved, or let it expire naturally.

Design constraints:
  - Requires --reason (empty/blank reasons are rejected).
  - Not an env var (cannot be set accidentally or chained).
  - Single operation: each git commit/push consumes one 5-minute window.
  - Auditable: every invocation is recorded in .atdd/emergency-audit.jsonl.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _find_repo_root(start: Path | None = None) -> Path | None:
    """Walk up from start (or cwd) to find the git repo root."""
    candidate = (start or Path.cwd()).resolve()
    for parent in [candidate, *candidate.parents]:
        if (parent / ".git").exists():
            return parent
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-10-31
        return None


def cmd_emergency(reason: str, repo_root: Path | None = None) -> None:
    """Create emergency bypass file and append audit record.

    Args:
        reason: Non-empty description of why the bypass is needed.
        repo_root: Override the repo root (for testing). Defaults to git root.

    Raises:
        ValueError: If reason is empty or whitespace-only.
        SystemExit(1): If the .atdd/ directory cannot be found/created.
    """
    reason = reason.strip()
    if not reason:
        raise ValueError(
            "Emergency bypass requires a non-empty reason.\n"
            "Example: atdd emergency --reason 'validator outage; tracked in #999'"
        )

    if repo_root is None:
        repo_root = _find_repo_root()
    if repo_root is None:
        print("ATDD: Cannot find git repo root. Run from inside a git repository.", file=sys.stderr)
        sys.exit(1)

    atdd_dir = repo_root / ".atdd"
    if not atdd_dir.exists():
        print(
            f"ATDD: .atdd/ directory not found at {atdd_dir}.\n"
            "Run `atdd init` first to set up the ATDD infrastructure.",
            file=sys.stderr,
        )
        sys.exit(1)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Write the bypass file (hooks check its mtime — always overwrite to reset TTL)
    bypass_file = atdd_dir / "EMERGENCY_BYPASS"
    bypass_file.write_text(
        f"reason={reason}\n"
        f"timestamp={ts}\n"
        f"pid={os.getpid()}\n",
        encoding="utf-8",
    )

    # Append audit record
    audit_log = atdd_dir / "emergency-audit.jsonl"
    record = json.dumps({
        "timestamp": ts,
        "reason": reason,
        "pid": os.getpid(),
        "cwd": str(Path.cwd()),
    })
    with audit_log.open("a", encoding="utf-8") as f:
        f.write(record + "\n")

    print(
        f"ATDD: Emergency bypass created (valid 5 min).\n"
        f"  Reason : {reason}\n"
        f"  File   : {bypass_file}\n"
        f"  Audit  : {audit_log}\n"
        f"\n"
        f"Run your git operation now. Remove .atdd/EMERGENCY_BYPASS when done.",
        file=sys.stderr,
    )


def run_cli(argv: list[str]) -> int:
    """Entry point for `atdd emergency`."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="atdd emergency",
        description=(
            "Create a single-use emergency bypass for ATDD hook gates (valid 5 min).\n"
            "\n"
            "All ATDD_SKIP_* env-var bypasses were retired in E030 (2026-05-26).\n"
            "This command is the ONLY sanctioned bypass for genuine emergencies.\n"
            "\n"
            "Example:\n"
            "  atdd emergency --reason 'validator outage; fix tracked in #999'\n"
            "  git push   # bypass active for 5 minutes\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--reason",
        required=True,
        help="Why the bypass is needed (non-empty, will be logged to emergency-audit.jsonl)",
    )
    args = parser.parse_args(argv)

    try:
        cmd_emergency(reason=args.reason)
    except ValueError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-10-31
        print(f"ATDD: {exc}", file=sys.stderr)
        return 1

    return 0
