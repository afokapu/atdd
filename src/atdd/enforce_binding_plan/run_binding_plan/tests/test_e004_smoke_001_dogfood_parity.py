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

FOUR FURTHER REGRESSIONS, NOW REAL PARITY (post ext re-vendor, PR #21 / ext main
0be85a4).  ``dead-code.reachability`` (ATDD_GRAPH_ROOTS), ``logging.print``
(ATDD_SCAN_EXCLUDES), ``metric-implementation-must-exist`` (callable resolution)
and ``refactor.composition-consumer`` (TS + Supabase legs) were DETECTOR-side
regressions whose parity could not close until the fixed detectors were
re-vendored. Each is now asserted as a real legacy-vs-runner diff (same anchor
pattern: common scope, real oracle, ``enforce()`` verdict, empty diff, load-bearing
control) by its own ``test_e004_..._runner_matches_legacy_over_*`` below.

TWO UNVERIFIED (reported honestly, never faked).  ``coach-ratchet-pres`` and
``live-smoke-acceptance-must-execute`` have no constructible same-input legacy
comparison (their oracles need an unbuilt resolver/consumer). They are enumerated
and SKIPPED with audit-cited reasons by ``test_e004_..._parity_unverified`` below
rather than being asserted parity-clean.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import shutil
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


# --------------------------------------------------------------------------- #
# REGRESSION rows promoted to REAL parity (post ext re-vendor, PR #21 / ext main
# 0be85a4). Each mirrors the sql-injection anchor: a common synthetic scope, the
# real legacy in-core oracle, the real ``enforce()`` runner verdict, a per-rule
# diff asserted empty, and a LOAD-BEARING control proving the carve/leg/root bites
# (a regressed input would break parity, so it can never sneak through).
# --------------------------------------------------------------------------- #
def _runner_verdict(scope: pathlib.Path, rule_id: str):
    """The real runner's per-rule verdict over ``scope`` (``atdd enforce`` path)."""
    from atdd.enforce.runner import enforce

    result = enforce(scope, path_override=["."])
    matches = [v for v in result.verdicts if v.rule_id == rule_id]
    assert matches, f"runner emitted no verdict for {rule_id!r} (bound set drifted?)"
    return matches[0]


def _raw_detector_records(
    scope: pathlib.Path, rule_id: str, env_extra: dict | None = None
) -> list[dict]:
    """RAW v1.1 records from the vendored provider CLI (the carve-less control)."""
    from atdd.enforce.runner import resolve_substrate_home

    home = resolve_substrate_home(scope)
    cli = (
        home / ".atdd" / "workspaces" / "atdd.workspace.python-pytest"
        / "0.1.0" / "cli" / "scan.py"
    )
    env = {
        **os.environ,
        "ATDD_SCAN_ROOTS": json.dumps([str(scope)]),
        "ATDD_IMPL_ID": rule_id,
        **(env_extra or {}),
    }
    proc = subprocess.run(
        [sys.executable, str(cli), "--impl", rule_id],
        env=env, capture_output=True, text=True,
    )
    return json.loads(proc.stdout.strip() or "[]")


def _scope_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """A fresh, symlink-resolved scope root.

    ``resolve()`` is load-bearing: on macOS ``tmp_path`` lives under the
    ``/var -> /private/var`` symlink, and the legacy TS resolver compares
    ``import.resolve()`` against an UN-resolved ``rglob`` file set — an unresolved
    root silently yields an empty import graph (false over-flag). The runner and
    every detector also normalize to real paths, so resolving here keeps both
    sides on the identical canonical tree.
    """
    scope = (tmp_path.resolve() / "scope")
    scope.mkdir()
    return scope


# ── REGRESSION row 1 — coder.dead-code.reachability (ATDD_GRAPH_ROOTS) ──────────
def _build_dead_code_scope(scope: pathlib.Path) -> None:
    (scope / "pyproject.toml").write_text(
        '[project]\nname = "parity"\nversion = "0.1.0"\n\n'
        '[project.scripts]\nparity-cli = "app:main"\n',
        encoding="utf-8",
    )
    (scope / "app.py").write_text(
        "from lib import helper\n\n\ndef main():\n    return helper()\n", encoding="utf-8")
    (scope / "lib.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (scope / "dead.py").write_text("def unused():\n    return 0\n", encoding="utf-8")
    # A natural graph root (conftest.py) that does NOT reach the entry chain, so
    # the carve-less control still has a root set and over-flags the entry module
    # rather than tripping the detector's "no roots -> emit nothing" safety guard.
    (scope / "conftest.py").write_text("collect_ignore: list = []\n", encoding="utf-8")


def _legacy_dead_code_flagged(scope: pathlib.Path) -> set[str]:
    """LEGACY oracle: the real reachability functions over ``scope``.

    The reachability ALGORITHM is run verbatim — legacy ``extract_imports_ast``
    (scope-tolerant via its ``root=`` kwarg), ``is_root_file``,
    ``find_reachable_files`` and ``build_reverse_graph`` (the forward+reverse BFS).
    Only the two pieces the legacy module hardcodes to its ``PYTHON_DIR`` /
    ``REPO_ROOT`` globals — the dotted-module→file mapping (``resolve_module_to_file``)
    and the ``[project.scripts]`` parse (``find_cli_entry_points``) — are reproduced
    inline over ``scope`` rather than monkeypatched (a SMOKE test must not patch a
    collaborator). The mapping/parse rules are ported verbatim.
    """
    import atdd.coder.validators.test_dead_code_python as legacy

    pyfiles = [p for p in scope.rglob("*.py") if "__pycache__" not in str(p)]
    fileset = set(pyfiles)

    def _resolve(module: str) -> set[pathlib.Path]:
        base = scope / pathlib.Path(*module.split("."))
        out: set[pathlib.Path] = set()
        if base.with_suffix(".py") in fileset:
            out.add(base.with_suffix(".py"))
        if (base / "__init__.py") in fileset:
            out.add(base / "__init__.py")
        return out

    graph: dict[pathlib.Path, set[pathlib.Path]] = {f: set() for f in pyfiles}
    for f in pyfiles:
        for module in legacy.extract_imports_ast(f, root=scope):
            graph[f] |= _resolve(module)

    roots = {f for f in pyfiles if legacy.is_root_file(f)}
    # Entry-point seeding: the same [project.scripts] module parse
    # legacy.find_cli_entry_points performs (it reads REPO_ROOT/pyproject.toml),
    # reproduced over scope/pyproject.toml.
    pyproject = scope / "pyproject.toml"
    if pyproject.is_file():
        in_scripts = False
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped == "[project.scripts]":
                in_scripts = True
                continue
            if in_scripts:
                if stripped.startswith("["):
                    break
                if "=" in stripped:
                    value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
                    roots |= _resolve(value.split(":")[0])

    reachable = legacy.find_reachable_files(roots, graph) | legacy.find_reachable_files(
        roots, legacy.build_reverse_graph(graph)
    )
    return {
        str(f.relative_to(scope))
        for f in pyfiles
        if f not in reachable and f.name != "__init__.py"
    }


def test_e004_smoke_001_runner_matches_legacy_over_dead_code_graph_roots(
    tmp_path,
) -> None:
    """PARITY-AUDIT-26 row 1 (REGRESSION) closed by ext re-vendor.

    The runner resolves the scanned tree's ``[project.scripts]`` modules and
    forwards them as ``ATDD_GRAPH_ROOTS``; the re-vendored dead-code detector now
    READS them, so a module reachable only via a console entry point is not dead.
    Both sides flag exactly the genuinely-unreferenced module.
    """
    rule = "coder.dead-code.reachability"
    scope = _scope_dir(tmp_path)
    _build_dead_code_scope(scope)

    runner_flagged = {_location_to_relpath(loc) for loc in _runner_verdict(scope, rule).locations}
    legacy_flagged = _legacy_dead_code_flagged(scope)

    assert runner_flagged == legacy_flagged, (
        "runner/legacy dead-code verdict diff is NOT empty:\n"
        f"  legacy   flagged: {sorted(legacy_flagged)}\n"
        f"  runner   flagged: {sorted(runner_flagged)}"
    )
    # The entry module + its entry-only-reachable import are suppressed on both
    # sides; only the truly-unreferenced module is flagged.
    assert "dead.py" in legacy_flagged
    assert "app.py" not in runner_flagged and "lib.py" not in runner_flagged

    # LOAD-BEARING control: the raw detector with NO graph roots over-flags the
    # entry module (it is unreachable from the natural conftest root). Equal sets
    # above are therefore a real signal — a detector that ignored ATDD_GRAPH_ROOTS
    # would break parity, not silently pass.
    raw_flagged = {r.get("file") for r in _raw_detector_records(scope, rule)
                   if r.get("rule_id") == rule}
    assert "app.py" in raw_flagged, (
        "control failed: the carve-less (no ATDD_GRAPH_ROOTS) detector did NOT "
        f"over-flag the entry module, so parity is not load-bearing: {sorted(raw_flagged)}"
    )


# ── REGRESSION row 9 — coder.logging.print (ATDD_SCAN_EXCLUDES) ─────────────────
def _build_print_scope(scope: pathlib.Path) -> None:
    (scope / "python").mkdir()
    (scope / "tools").mkdir()
    (scope / ".atdd").mkdir()
    # Production print() under python/ — flagged by both sides.
    (scope / "python" / "prod.py").write_text(
        "def boot():\n    print('hello')\n", encoding="utf-8")
    # print() OUTSIDE python/ — invisible to the python/-scoped legacy validator;
    # the runner suppresses it via the configured exclude glob. Same verdict set.
    (scope / "tools" / "codegen.py").write_text(
        "def gen():\n    print('generated')\n", encoding="utf-8")
    (scope / ".atdd" / "config.yaml").write_text(
        "version: '1.0'\nscan:\n  rules:\n    coder.logging.print:\n"
        "      excludes:\n        - 'tools/**'\n",
        encoding="utf-8",
    )


def _legacy_print_flagged(scope: pathlib.Path) -> set[str]:
    """LEGACY oracle: the real ``scan_print_in_production`` (scopes to ``python/``,
    AST ``print()`` detection) — its directory scoping is its exclusion mechanism."""
    import atdd.coder.validators.test_structured_logging as legacy

    _, violations = legacy.scan_print_in_production(scope)
    return {v.location.rsplit(":", 2)[0] for v in violations}


def test_e004_smoke_001_runner_matches_legacy_over_print_excludes(tmp_path) -> None:
    """PARITY-AUDIT-26 row 9 (REGRESSION) closed by ext re-vendor.

    The re-vendored print report channel now forwards ``ATDD_SCAN_EXCLUDES`` to
    the detector. The runner's configured exclude suppresses the same out-of-tree
    file the python/-scoped legacy validator never sees — the per-rule diff over
    the production sink is empty.
    """
    rule = "coder.logging.print"
    scope = _scope_dir(tmp_path)
    _build_print_scope(scope)

    runner_flagged = {_location_to_relpath(loc) for loc in _runner_verdict(scope, rule).locations}
    legacy_flagged = _legacy_print_flagged(scope)

    assert runner_flagged == legacy_flagged, (
        "runner/legacy print verdict diff is NOT empty:\n"
        f"  legacy flagged: {sorted(legacy_flagged)}\n"
        f"  runner flagged: {sorted(runner_flagged)}"
    )
    assert "python/prod.py" in legacy_flagged and "python/prod.py" in runner_flagged
    assert "tools/codegen.py" not in runner_flagged

    # LOAD-BEARING control: without the exclude the raw detector over-flags the
    # out-of-tree file — proving the runner is actually honoring excludes.
    raw_flagged = {r.get("file") for r in _raw_detector_records(scope, rule)
                   if r.get("rule_id") == rule}
    assert "tools/codegen.py" in raw_flagged, (
        "control failed: the carve-less (no ATDD_SCAN_EXCLUDES) detector did NOT "
        f"over-flag the excluded file, so parity is not load-bearing: {sorted(raw_flagged)}"
    )


# ── REGRESSION row 23 — metric-implementation-must-exist (callable resolution) ──
_METRIC_RULE = "tester.acceptance-violation.metric-implementation-must-exist"
# Names are deliberately ``par_``-prefixed so neither side resolves them via the
# real toolkit metrics dir (src/atdd/runners/metrics) — both rely solely on the
# scope-local .atdd/metrics, keeping the oracle and runner on one input.
_VALID_METRICS = ("par_lambda_rate", "par_imported_rate", "par_nopasses_rate")


def _build_metric_scope(scope: pathlib.Path) -> None:
    plan_dir = scope / "plan" / "parity_metric"
    plan_dir.mkdir(parents=True)
    metrics = scope / ".atdd" / "metrics"
    metrics.mkdir(parents=True)

    def acc(suffix: str, metric: str) -> str:
        return (
            f"  - identity:\n"
            f'      urn: "acc:parity-metric:{suffix}"\n'
            f'      id: "AC-{suffix}"\n'
            f'      phase: "GREEN"\n'
            f"    signal:\n"
            f'      metric: "{metric}"\n'
            f"      threshold: 0.5\n"
        )

    plan = (
        'urn: "wmbt:parity-metric:E001"\n'
        'step: "define"\n'
        'statement: "metric-implementation parity fixture"\n'
        "acceptances:\n"
        + acc("E001-METRIC-001-lambda", "par_lambda_rate")
        + acc("E002-METRIC-002-imported", "par_imported_rate")
        + acc("E003-METRIC-003-nopasses", "par_nopasses_rate")
        + acc("E004-METRIC-004-broken", "par_broken_rate")
    )
    (plan_dir / "E001.yaml").write_text(plan, encoding="utf-8")

    # Three callables the OLD `^def compute`/`^def passes` regex would mis-handle,
    # all of which resolve under callable(compute) (legacy + re-vendored detector).
    (metrics / "par_lambda_rate.py").write_text(
        "compute = lambda repo_root: 0  # noqa: E731\n", encoding="utf-8")
    (metrics / "par_imported_rate.py").write_text(
        "from statistics import fmean as compute\n", encoding="utf-8")
    (metrics / "par_nopasses_rate.py").write_text(
        "from pathlib import Path\n\n\ndef compute(repo_root: Path) -> int:\n    return 0\n",
        encoding="utf-8")
    # The ONLY real violation: a module that EXISTS but fails to import.
    (metrics / "par_broken_rate.py").write_text(
        "import _atdd_nonexistent_parity_dep_xyz  # noqa: F401\n\n\n"
        "def compute(repo_root):\n    return 0\n",
        encoding="utf-8")


def _legacy_metric_flagged(scope: pathlib.Path) -> set[str]:
    """LEGACY oracle: the real ``collect_violations`` (find_repo_rules over plan/ +
    discover_metric_module's import + callable(compute) resolution)."""
    import atdd.tester.validators.test_metric_implementation as legacy

    flagged: set[str] = set()
    for v in legacy.collect_violations(repo_root=scope):
        mo = re.search(r"signal\.metric=['\"]([^'\"]+)['\"]", v.detail)
        if mo:
            flagged.add(mo.group(1))
    return flagged


def _runner_metric_flagged(scope: pathlib.Path, verdict) -> set[str]:
    """Map each runner-flagged ``file:line`` back to its ``metric:`` declaration —
    the detector emits the line of the declaration, so this is deterministic."""
    flagged: set[str] = set()
    for loc in verdict.locations:
        relpath = _location_to_relpath(loc)
        lineno = int(loc.rsplit(":", 2)[1])
        line = (scope / relpath).read_text(encoding="utf-8").splitlines()[lineno - 1]
        mo = re.search(r"metric:\s*['\"]?(\w+)", line)
        if mo:
            flagged.add(mo.group(1))
    return flagged


def test_e004_smoke_001_runner_matches_legacy_over_metric_callable_resolution(
    tmp_path,
) -> None:
    """PARITY-AUDIT-26 row 23 (REGRESSION) closed by ext re-vendor.

    The re-vendored detector resolves a metric's ``compute`` by import +
    ``callable()`` over the registry (matching legacy ``discover_metric_module``),
    replacing the brittle ``^def compute``/``^def passes`` regex. Lambda / imported
    / no-``passes`` callables VALIDATE on both sides; only the import-failing module
    is flagged.
    """
    scope = _scope_dir(tmp_path)
    _build_metric_scope(scope)

    runner_flagged = _runner_metric_flagged(scope, _runner_verdict(scope, _METRIC_RULE))
    legacy_flagged = _legacy_metric_flagged(scope)

    assert runner_flagged == legacy_flagged == {"par_broken_rate"}, (
        "runner/legacy metric verdict diff is NOT empty (expected {'par_broken_rate'}):\n"
        f"  legacy flagged: {sorted(legacy_flagged)}\n"
        f"  runner flagged: {sorted(runner_flagged)}"
    )

    # LOAD-BEARING control: the regressed `^def compute`/`^def passes` regex would
    # over-flag every valid callable (lambda/imported have no `def compute`;
    # nopasses has no `def passes`), yet callable resolution validates all three.
    regex_flagged = set()
    for name in _VALID_METRICS:
        src = (scope / ".atdd" / "metrics" / f"{name}.py").read_text(encoding="utf-8")
        if not re.search(r"^def compute", src, re.M) or not re.search(r"^def passes", src, re.M):
            regex_flagged.add(name)
    assert set(_VALID_METRICS) <= regex_flagged, (
        "control failed: the naive regex did not over-flag the valid callables, so "
        f"callable resolution is not load-bearing: {sorted(regex_flagged)}"
    )
    assert not (set(_VALID_METRICS) & (legacy_flagged | runner_flagged))


# ── REGRESSION row 13 — composition-consumer (TypeScript + Supabase legs) ───────
_COMPOSITION_RULE = "coder.refactor.composition-consumer"


def _composition_detector_dir() -> pathlib.Path:
    from atdd.enforce.runner import resolve_substrate_home

    home = resolve_substrate_home(repo_src().parent)
    return (
        home / ".atdd" / "workspaces" / "atdd.workspace.python-pytest" / "0.1.0"
        / "implementations" / "composition_completeness_detector"
    )


def _build_composition_scope(scope: pathlib.Path) -> None:
    """Common scope = the vendored detector's own dirty fixtures (a TS type-only
    consumer violation + a Supabase integration-never-imported violation)."""
    fixtures = _composition_detector_dir() / "fixtures"
    shutil.copytree(fixtures / "typescript_dirty" / "web", scope / "web")
    shutil.copytree(fixtures / "supabase_dirty" / "supabase", scope / "supabase")


def _legacy_composition_flagged(scope: pathlib.Path) -> set[str]:
    """LEGACY oracle: the real ``analyze_typescript_repo`` over both polyglot
    stacks. Location is feature-relative (``<feature>/<layer>/<file>``)."""
    import atdd.coder.validators.test_composition_completeness as legacy

    flagged: set[str] = set()
    for stack in ("typescript", "supabase"):
        for v in legacy.analyze_typescript_repo(scope, stack=stack):
            if v.rule_id == _COMPOSITION_RULE:
                flagged.add(v.location)
    return flagged


def _strip_stack_prefix(relpath: str) -> str:
    """``web/src/<feature>/...`` / ``supabase/functions/<feature>/...`` ->
    feature-relative, matching the legacy oracle's location form."""
    return relpath.replace("web/src/", "").replace("supabase/functions/", "")


def test_e004_smoke_001_runner_matches_legacy_over_composition_polyglot(tmp_path) -> None:
    """PARITY-AUDIT-26 row 13 (REGRESSION) closed by ext re-vendor.

    The re-vendored detector realizes the TypeScript + Supabase legs (previously
    Python-only), so the runner now enforces ``composition-consumer`` across the
    same polyglot stacks as legacy ``analyze_typescript_repo`` — identical flagged
    set over a common scope.
    """
    scope = _scope_dir(tmp_path)
    _build_composition_scope(scope)

    runner_flagged = {
        _strip_stack_prefix(_location_to_relpath(loc))
        for loc in _runner_verdict(scope, _COMPOSITION_RULE).locations
    }
    legacy_flagged = _legacy_composition_flagged(scope)

    assert runner_flagged == legacy_flagged, (
        "runner/legacy composition verdict diff is NOT empty:\n"
        f"  legacy flagged: {sorted(legacy_flagged)}\n"
        f"  runner flagged: {sorted(runner_flagged)}"
    )
    assert legacy_flagged, "scope produced no composition violations (fixture drift?)"

    # LOAD-BEARING control: the Python-only leg (the pre-re-vendor behavior) finds
    # NONE of the TS/Supabase violations — proving the re-vendored polyglot legs
    # are what close parity, not the pre-existing Python leg. The vendored detector
    # is pure-stdlib, so it loads via an isolated spec (no sys.path mutation).
    det_file = _composition_detector_dir() / "composition_completeness.py"
    spec = importlib.util.spec_from_file_location("parity_composition_detector", det_file)
    detector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(detector)
    py_only = [v for v in detector.scan_python(scope) if v["rule_id"] == _COMPOSITION_RULE]
    assert not py_only, (
        "control failed: the Python-only leg flagged a TS/Supabase file, so the "
        f"polyglot legs are not load-bearing for parity: {py_only}"
    )


# Bound rules whose extension-vs-legacy parity CANNOT be asserted clean here, with
# the precise reason (audit-cited). Skipped — never faked to exit 0. The four
# REGRESSION rows above are now REAL parity diffs (closed by the ext re-vendor,
# PR #21 / ext main 0be85a4); the two rows below remain UNVERIFIED — no same-input
# legacy comparison is constructible until an upstream resolver/consumer exists.
_AWAITS_REVENDOR = [
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
def test_e004_smoke_001_parity_unverified(rule_id, reason) -> None:
    """Surface (not fake) the rules whose parity has no constructible oracle."""
    pytest.skip(f"{rule_id}: {reason}")
