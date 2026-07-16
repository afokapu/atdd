# URN: component:enforce-binding-plan:run-binding-plan:cli:cli:adapter
# Runtime: python
# Purpose: Thin argv adapter for `atdd enforce` — parse flags, dispatch to the
#          runner, map the aggregate verdict to a process exit code (0/1/2).
"""``atdd enforce`` CLI surface (#1238).

    atdd enforce [--paths P ...] [--repo-root DIR] [--conformance] [--verify-substrate]
                 [--ratchet PATH] [--record-ratchet PATH]

  * (default)            run the binding plan over the consumer's code; exit
                         0 (all pass) / 1 (any strict rule fails) / 2 (usage).
  * ``--paths``          scan these repo-relative paths instead of the config
                         roots (operator/CI scoping; dogfood: ``--paths src/atdd``).
  * ``--conformance``    V1 check — is every bound rule runnable end-to-end?
  * ``--verify-substrate`` V6 guard — vendored trees present + digest-matched.
  * ``--ratchet``        judge the verdict against a recorded per-rule violation
                         baseline: pre-existing debt is held FLAT, a rule ABOVE
                         its baseline fails. This is what lets the CI job be
                         BLOCKING without reding the build on known debt (#1428).
  * ``--record-ratchet`` write the current failing counts to PATH as the baseline.

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
    parser.add_argument(
        "--ratchet", default=None, metavar="PATH",
        help=(
            "Judge the verdict against a ratchet baseline: a rule at or below its "
            "recorded violation count is held FLAT (pre-existing debt), a rule above "
            "it FAILS. This is what lets the CI job be blocking without reding the "
            "build on known debt (#1428)."
        ),
    )
    parser.add_argument(
        "--record-ratchet", default=None, metavar="PATH", dest="record_ratchet",
        help=(
            "Record the CURRENT failing-violation counts to PATH as a ratchet "
            "baseline, then exit 0. Use to pay debt down, NEVER to green a red build."
        ),
    )
    return parser


class _RatchetUsageError(Exception):
    """A bad/absent ratchet baseline — a usage error (exit 2), not a verdict."""


def _resolve(repo_root: Path, path: str) -> Path:
    """Resolve a CLI path argument against the repo root when it is relative."""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else repo_root / candidate


def _record_ratchet(result, repo_root: Path, dest_arg: str, paths) -> int:
    """Write the current failing counts to *dest_arg* as the ratchet baseline."""
    from atdd.enforce.ratchet import record_baseline

    dest = _resolve(repo_root, dest_arg)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(record_baseline(result, scope=list(paths or [])), encoding="utf-8")
    print(result.report)
    print(f"\nratchet baseline recorded: {dest}")
    return 0


def _apply_ratchet(result, repo_root: Path, ratchet_arg: str):
    """Re-judge *result* against the recorded baseline; pre-existing debt is held flat."""
    from atdd.enforce.ratchet import RatchetError, apply_ratchet, load_baseline

    try:
        baseline = load_baseline(_resolve(repo_root, ratchet_arg))
    except RatchetError as exc:
        raise _RatchetUsageError(str(exc)) from exc
    return apply_ratchet(result, baseline)


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

    if args.record_ratchet:
        return _record_ratchet(result, repo_root, args.record_ratchet, args.paths)

    if args.ratchet:
        try:
            result = _apply_ratchet(result, repo_root, args.ratchet)
        except _RatchetUsageError as exc:
            _log.warning("enforce ratchet error", extra={"error": str(exc)})
            print(f"atdd enforce: {exc}")
            return 2

    print(result.report)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(run())
