# URN: test:enforce-binding-plan:run-binding-plan:E004-SMOKE-001-dogfood-parity
# Acceptance: acc:enforce-binding-plan:E004-SMOKE-001-dogfood-parity
# WMBT: wmbt:enforce-binding-plan:E004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E004-SMOKE-001 — REAL legacy-vs-extension verdict parity over a common scope (V4).

WHY THIS TEST WAS REWRITTEN (justified correction of a hollow acceptance).
The prior implementation asserted ``proc.returncode == 0`` over ``src/atdd`` and
``"coder.logging.print" not in output``. Per ``docs/PARITY-AUDIT-26.md``
cross-cutting finding 1, that establishes NO parity on three compounding layers:

  1. the legacy in-core coder validators are hardcoded to consumer-layout dirs
     (``REPO_ROOT/python``, ``web``, ``supabase`` …) — NONE of which exist in the
     toolkit repo, so "src/atdd is clean under legacy" is true by *vacuity*, the
     oracle is never actually run;
  2. exit-0 over src/atdd is not a parity signal — it conflates unrunnable/exempt
     rules with passing ones;
  3. legacy was never invoked, so "the diff vs legacy is empty" was never tested.

This rewrite makes E004 do what the acceptance promises: compute the EXTENSION
verdict and the LEGACY verdict over the SAME files and assert the per-rule diff
is empty. The diff is anchored on ``coder.security.sql-injection`` because that
rule (a) is one of the carve REGRESSIONS the core-side fix restores, and (b) the
legacy in-core validator exposes a real, callable detection function
(``test_security_patterns.check_sql_concatenation`` + ``find_python_files`` with
the convention's exclusions) — a genuine oracle, not a hand-authored expectation.

THE COMMON SCOPE.  A synthetic tree with the SAME dynamic-SQL sink in two places:
``pkg/orders.py`` (production — both sides must flag) and
``pkg/tests/test_orders.py`` (a test file the legacy security convention EXCLUDES
via ``**/tests/**`` / ``**/test_*.py``). The hermetic detector dropped that
exclusion carve onto the caller; ``compute_scan_policy`` re-supplies it
(``_RULE_DEFAULT_EXCLUDES``). Parity holds iff the runner — which applies the
carve — reproduces legacy's suppression of the test file while still flagging the
production file.

LOAD-BEARING (not vacuous).  A control leg runs the RAW detector (no carve) over
the same tree and asserts it over-flags the test file — proving the parity
assertion would FAIL if the carve regressed, so exit-0 can never sneak through.

EXTENSION SIDE = the real runner.  ``enforce()`` is the exact function the
``atdd enforce`` CLI dispatches to (the verb/exit-code wiring is covered by
E002/E003); calling it in-process yields STRUCTURED per-rule verdicts, which a
precise per-rule diff needs (text-parsing the report would be the fragile path).

AWAITS EXT RE-VENDOR (reported honestly, never faked).  Four bound rules are
DETECTOR-side regressions whose parity cannot close until the fixed detectors are
re-vendored from the parallel atdd-extensions PR (a convergence step the overseer
runs; the vendored trees here are digest-locked). Two further rules are UNVERIFIED
— no same-input legacy comparison is constructible. Those six are enumerated and
SKIPPED with audit-cited reasons by
``test_e004_..._await_revendor`` below rather than being asserted parity-clean.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

from .conftest import repo_src

pytestmark = pytest.mark.smoke

_SQL_RULE = "coder.security.sql-injection"

# A dynamic-SQL sink the legacy ``check_sql_concatenation`` AST detector flags
# (f-string with a SQL keyword passed to ``.execute()``) — identical content in
# the production file and the excluded test file, so the ONLY thing that can
# suppress the test file is the relocated exclusion carve.
_DYN_SQL = (
    "def run(db, uid):\n"
    '    return db.execute(f"SELECT * FROM users WHERE id={uid}")\n'
)


def _build_common_scope(tmp_path: pathlib.Path) -> pathlib.Path:
    """A tree both sides can scan: prod file (flag) + in-``tests/`` file (carve)."""
    root = tmp_path / "scope"
    (root / "pkg" / "tests").mkdir(parents=True)
    (root / "pkg" / "orders.py").write_text(_DYN_SQL, encoding="utf-8")
    (root / "pkg" / "tests" / "test_orders.py").write_text(_DYN_SQL, encoding="utf-8")
    return root


def _legacy_sql_flagged(scope: pathlib.Path) -> set[str]:
    """LEGACY oracle: the real in-core validator over ``scope`` (scope-relative)."""
    from atdd.coder.validators import test_security_patterns as legacy

    conv = legacy.load_security_convention()
    rule = conv.get("rules", {}).get("sql_injection", {})
    keywords = rule.get("sql_keywords")
    sinks = rule.get("sink_methods")
    exclusions = rule.get("exclusions", [])
    flagged: set[str] = set()
    for f in legacy.find_python_files(scope, exclusions):
        if legacy.check_sql_concatenation(f, keywords, sinks):
            flagged.add(str(f.relative_to(scope)))
    return flagged


def _location_to_relpath(location: str) -> str:
    """``pkg/orders.py:2:22`` -> ``pkg/orders.py`` (strip the ``:line:col`` tail)."""
    parts = location.rsplit(":", 2)
    return parts[0] if len(parts) == 3 else location


def _extension_sql_flagged(scope: pathlib.Path) -> set[str]:
    """EXTENSION verdict: the real runner over ``scope`` (scan-root-relative)."""
    from atdd.enforce.runner import enforce

    result = enforce(scope, path_override=["."])
    sql = [v for v in result.verdicts if v.rule_id == _SQL_RULE]
    assert sql, f"runner emitted no verdict for {_SQL_RULE!r} (bound set drifted?)"
    return {_location_to_relpath(loc) for loc in sql[0].locations}


def _raw_detector_sql_flagged(scope: pathlib.Path) -> set[str]:
    """CONTROL: the raw provider detector with NO carve excludes (over-flags)."""
    from atdd.enforce.runner import resolve_substrate_home

    home = resolve_substrate_home(scope)
    cli = (
        home / ".atdd" / "workspaces" / "atdd.workspace.python-pytest"
        / "0.1.0" / "cli" / "scan.py"
    )
    env = {
        **os.environ,
        "ATDD_SCAN_ROOTS": json.dumps([str(scope)]),
        "ATDD_IMPL_ID": _SQL_RULE,
        # deliberately NO ATDD_SCAN_EXCLUDES — this is the carve-less baseline.
    }
    proc = subprocess.run(
        [sys.executable, str(cli), "--impl", _SQL_RULE],
        env=env, capture_output=True, text=True,
    )
    records = json.loads(proc.stdout.strip() or "[]")
    return {r.get("file") for r in records if r.get("rule_id") == _SQL_RULE}


def test_e004_smoke_001_runner_matches_legacy_over_sql_injection_carve(tmp_path) -> None:
    scope = _build_common_scope(tmp_path)
    prod = "pkg/orders.py"
    excluded = "pkg/tests/test_orders.py"

    legacy_flagged = _legacy_sql_flagged(scope)
    extension_flagged = _extension_sql_flagged(scope)

    # PARITY: the runner's verdict set EQUALS the legacy validator's verdict set
    # over the identical files — the per-rule diff is empty (the acceptance).
    assert extension_flagged == legacy_flagged, (
        "extension/legacy SQL-injection verdict diff is NOT empty:\n"
        f"  legacy   flagged: {sorted(legacy_flagged)}\n"
        f"  extension flagged: {sorted(extension_flagged)}"
    )
    # Both sides flag the production sink and BOTH suppress the in-tests/ file
    # (the relocated ``**/tests/**`` carve is preserved by compute_scan_policy).
    assert prod in legacy_flagged and prod in extension_flagged
    assert excluded not in legacy_flagged and excluded not in extension_flagged

    # LOAD-BEARING control: without the carve the raw detector over-flags the test
    # file. Equal sets above are therefore a real signal — a regressed carve would
    # break parity, not silently pass.
    raw_flagged = _raw_detector_sql_flagged(scope)
    assert excluded in raw_flagged, (
        "control failed: the raw (carve-less) detector did NOT over-flag the "
        "excluded test file, so the parity assertion is not load-bearing:\n"
        f"  raw flagged: {sorted(raw_flagged)}"
    )


def test_e004_smoke_001_sql_carve_reproduces_legacy_security_convention() -> None:
    """The relocated carve is the legacy convention's exclusion list, verbatim.

    Grounds the carve parity in the LIVE legacy source (the security convention),
    not an invented constant: ``compute_scan_policy``'s default excludes for
    ``coder.security.sql-injection`` must equal
    ``security.rules.sql_injection.exclusions`` — the knowledge the hermetic
    detector dropped onto the caller.
    """
    import atdd
    import yaml

    from atdd.enforce.conventions import compute_scan_policy

    conv_path = (
        pathlib.Path(atdd.__file__).resolve().parent
        / "coder" / "conventions" / "security.convention.yaml"
    )
    conv = yaml.safe_load(conv_path.read_text(encoding="utf-8"))
    legacy_exclusions = conv["security"]["rules"]["sql_injection"]["exclusions"]

    policy = compute_scan_policy(
        repo_src().parent, {}, _SQL_RULE, path_override=["."]
    )
    # Every legacy exclusion is re-supplied by the caller (the carve restores it).
    assert set(legacy_exclusions).issubset(set(policy.scan_excludes)), (
        "compute_scan_policy dropped a legacy SQL exclusion carve:\n"
        f"  legacy convention: {legacy_exclusions}\n"
        f"  policy excludes:   {policy.scan_excludes}"
    )


# Bound rules whose extension-vs-legacy parity CANNOT be asserted clean here, with
# the precise reason (audit-cited). Skipped — never faked to exit 0. When the
# parallel atdd-extensions PR is re-vendored (the overseer's convergence step),
# the four REGRESSION rows become diffable and these skips should be promoted to
# real diffs; the two UNVERIFIED rows need an upstream resolver first.
_AWAITS_REVENDOR = [
    pytest.param(
        "coder.dead-code.reachability",
        "REGRESSION (PARITY-AUDIT-26 row 1): the enforce layer now supplies "
        "pyproject [project.scripts] entry-point graph roots, but the vendored "
        "dead-code detector does not yet READ ATDD_GRAPH_ROOTS — parity closes "
        "only on ext re-vendor.",
        id="dead-code.reachability",
    ),
    pytest.param(
        "coder.logging.print",
        "REGRESSION (PARITY-AUDIT-26 row 9): the print report test does not "
        "forward ATDD_SCAN_EXCLUDES, so excludes are ignored until ext re-vendor.",
        id="logging.print",
    ),
    pytest.param(
        "tester.acceptance-violation.metric-implementation-must-exist",
        "REGRESSION (PARITY-AUDIT-26 row 23): regex `^def compute`+`^def passes` "
        "over raw YAML replaced legacy callable(compute) over the registry "
        "(adds FPs, misses imports) — awaits ext re-vendor.",
        id="metric-implementation",
    ),
    pytest.param(
        "coder.refactor.composition-consumer",
        "REGRESSION (PARITY-AUDIT-26 row 13): ext realizes only the Python leg; "
        "legacy enforces the same rule across python+typescript+supabase — "
        "polyglot parity awaits the TS/Supabase legs re-vendor.",
        id="composition-consumer",
    ),
    pytest.param(
        "coder.refactor.coach-ratchet-pres",
        "UNVERIFIED (PARITY-AUDIT-26): legacy's verdict needs a git-diff reduction "
        "scan + a smoke-evidence gate, both externalized to an unbuilt "
        "resolver/consumer — no end-to-end diff is exercisable.",
        id="coach-ratchet-pres",
    ),
    pytest.param(
        "tester.acceptance-violation.live-smoke-acceptance-must-execute",
        "UNVERIFIED (PARITY-AUDIT-26): live_smoke authority differs (legacy plan "
        "execution_kind+URN-join vs ext in-file header) — no clean same-input "
        "comparison is constructible.",
        id="live-smoke-execution",
    ),
]


@pytest.mark.parametrize("rule_id,reason", _AWAITS_REVENDOR)
def test_e004_smoke_001_parity_awaits_ext_revendor(rule_id, reason) -> None:
    """Surface (not fake) the rules whose parity cannot yet be asserted clean."""
    pytest.skip(f"{rule_id}: {reason}")
