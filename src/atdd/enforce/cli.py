# URN: component:enforce-binding-plan:run-binding-plan:cli:cli:adapter
# Runtime: python
# Purpose: Thin argv adapter for `atdd enforce` — parse flags, dispatch to the
#          runner, map the aggregate verdict to a process exit code (0/1/2).
"""``atdd enforce`` CLI surface (#1238).

    atdd enforce [--paths P ...] [--repo-root DIR] [--conformance] [--verify-substrate]

  * (default)            run the binding plan over the consumer's code; exit
                         0 (all pass) / 1 (any strict rule fails) / 2 (usage).
  * ``--paths``          scan these repo-relative paths instead of the config
                         roots (operator/CI scoping; dogfood: ``--paths src/atdd``).
  * ``--conformance``    V1 check — is every bound rule runnable end-to-end?
  * ``--verify-substrate`` V6 guard — vendored trees present + digest-matched.

Exit code: 0 (pass / clean) / 1 (verdict FAIL or guard mismatch) / 2 (usage —
could not run as configured: malformed config/lock, unresolvable provider).
The commit hook / CI job invokes this same primitive and gates on its exit code.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional, Sequence

_log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd enforce",
        description=(
            "Lock-driven extension enforcement: read binding.lock.yaml, resolve each "
            "bound convention's workspace provider, scan the consumer's code over a "
            "subprocess, and produce one PASS/FAIL verdict + exit code (#1238)."
        ),
    )
    parser.add_argument(
        "--repo-root", default=None,
        help="Consumer repo root under inspection (default: cwd).",
    )
    parser.add_argument(
        "--paths", nargs="+", default=None, dest="paths",
        help="Repo-relative paths to scan instead of the configured roots.",
    )
    parser.add_argument(
        "--conformance", action="store_true",
        help="V1: report whether every bound rule is runnable end-to-end.",
    )
    parser.add_argument(
        "--verify-substrate", action="store_true", dest="verify_substrate",
        help="V6: verify the vendored substrate trees match substrate.lock.yaml.",
    )
    return parser


def run(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point invoked by ``atdd.cli`` for ``atdd enforce ...``."""
    args = _build_parser().parse_args(list(argv or []))
    repo_root = Path(args.repo_root) if args.repo_root else Path.cwd()

    # Imports are local so a bare `--help` never touches the runtime.
    from atdd.enforce.runner import EnforceUsageError, conformance, enforce

    if args.verify_substrate:
        from atdd.enforce.substrate_guard import verify_substrate

        ok, verdicts = verify_substrate(repo_root.resolve())
        for v in verdicts:
            print(f"[{'OK' if v.ok else 'TAMPERED'}] {v.artifact_id} ({v.installed_path}): {v.detail}")
        print(f"verify-substrate: {'PASS' if ok else 'FAIL'} — {len(verdicts)} artifact(s).")
        return 0 if ok else 1

    if args.conformance:
        try:
            ok, report = conformance(repo_root)
        except EnforceUsageError as exc:
            _log.warning("enforce conformance usage error", extra={"error": str(exc)})
            print(f"atdd enforce: {exc}")
            return 2
        print(report)
        return 0 if ok else 1

    try:
        result = enforce(repo_root, path_override=args.paths)
    except EnforceUsageError as exc:
        _log.warning("enforce usage error", extra={"error": str(exc)})
        print(f"atdd enforce: {exc}")
        return 2

    print(result.report)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(run())
