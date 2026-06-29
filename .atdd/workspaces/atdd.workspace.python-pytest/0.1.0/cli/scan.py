#!/usr/bin/env python3
"""CW-Phase 0 provider CLI — the SUBPROCESS boundary between ATDD core and the
python-pytest workspace provider.

This is the black box core shells out to. It resolves a discovered detector
implementation and runs it over caller-supplied consumer scan roots, then prints
the RAW v1.1 violation list to stdout. The provider applies ZERO disposition; the
verdict is the consumer's job (core ``disposition_gate``).

================================  CLI CONTRACT  ================================

INVOCATION
    python3 scan.py [--impl <implementation_id>] [<scan_root> ...]

INPUT
    env ATDD_SCAN_ROOTS     JSON array of path strings — the consumer
                            code-under-inspection roots. Absolute paths are used
                            verbatim (a real consumer repo); relative resolve
                            against the implementation dir (fixtures). Positional
                            argv roots, if given, OVERRIDE this env var.
    env ATDD_SCAN_EXCLUDES  JSON array of exclusion globs (optional; forwarded to
                            the detector — note the v1.0.0 print detector ignores
                            it, see test_logging_print_report.py).
    env ATDD_IMPL_ID        implementation_id to resolve + run. Default
                            ``coder.logging.print``. ``--impl`` overrides.

OUTPUT  (stdout — the ONLY thing that crosses the boundary)
    A single JSON array of RAW v1.1 violation records, each:
        {rule_id, file, line, col, evidence, source_line}
    (PROVIDER-CONTRACT-v1.1.md §3.2). RAW factual channel only — no disposition.

DIAGNOSTICS  (stderr — never pollutes the stdout JSON)
    one ``provider-cli: ...`` run-health line (structured/ran/exit/count).

EXIT CODE
    0   the provider ran and emitted its report (run-health) — NOT a verdict.
    2   resolution / usage error (no scan roots; impl not discoverable; report
        test missing). stdout stays empty so the consumer's json.loads is safe.

BOUNDARY DISCIPLINE
    Imports ONLY the provider's own adapter (adapter/discover.py + run.py). It
    never imports ATDD core; core never imports this module. Provider-agnostic by
    construction: core knows only "run a CLI, read v1.1 JSON".
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_WS = Path(__file__).resolve().parent.parent  # atdd.workspace.python-pytest/
sys.path.insert(0, str(_WS / "adapter"))

import discover as discover_mod  # noqa: E402
import run as run_mod  # noqa: E402

IMPLS_ROOT = _WS / "implementations"
DEFAULT_IMPL = "coder.logging.print"
# The v1.1 report-emitting enforcement collected for the print impl.
REPORT_TEST = "test_logging_print_report.py"


def _scan_roots(argv_roots: list[str]) -> list[str]:
    if argv_roots:
        return list(argv_roots)
    raw = os.environ.get("ATDD_SCAN_ROOTS")
    if not raw:
        return []
    try:
        names = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(n) for n in names] if isinstance(names, list) else []


def _exclude_globs() -> list[str] | None:
    raw = os.environ.get("ATDD_SCAN_EXCLUDES")
    if not raw:
        return None
    try:
        globs = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return [str(g) for g in globs] if isinstance(globs, list) else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CW-Phase 0 python-pytest provider CLI")
    ap.add_argument("--impl", default=os.environ.get("ATDD_IMPL_ID", DEFAULT_IMPL))
    ap.add_argument("scan_roots", nargs="*")
    args = ap.parse_args(argv)

    roots = _scan_roots(args.scan_roots)
    if not roots:
        print("provider-cli: no scan roots (set ATDD_SCAN_ROOTS or pass argv)", file=sys.stderr)
        return 2

    # Resolution via the real provider contract: discover the implementation.
    found = discover_mod.discover_implementations(IMPLS_ROOT)
    impl = next((i for i in found if i.implementation_id == args.impl), None)
    if impl is None:
        ids = ", ".join(sorted(i.implementation_id for i in found))
        print(f"provider-cli: impl {args.impl!r} not discoverable under {IMPLS_ROOT} "
              f"(found: {ids})", file=sys.stderr)
        return 2

    impl_dir = impl.manifest_path.parent
    test_path = impl_dir / REPORT_TEST
    if not test_path.is_file():
        print(f"provider-cli: v1.1 report test {test_path} missing", file=sys.stderr)
        return 2

    result = run_mod.run_implementation(
        impl.implementation_id,
        test_path,
        scan_roots=roots,
        exclude_globs=_exclude_globs(),
    )

    # RAW factual channel only — no disposition applied here.
    json.dump(result.violations, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()

    print(
        f"provider-cli: impl={impl.implementation_id} structured={result.structured} "
        f"ran={result.ran} exit={result.exit_code} raw_violations={len(result.violations)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
