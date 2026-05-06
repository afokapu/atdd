# URN: component:govern-lifecycle:enforcement-substrate:harness-plugin:backend:integration
# Runtime: python
# Purpose: Pytest plugin that anchors test failures to substrate rule-IDs and routes them through the disposition gate (spec v12 §4.5, §7.2).

"""Harness-mode runner — pytest plugin (issue #411, spec v12 §7.2).

For every collected test that carries an ``# Acceptance: <acc:URN>`` header,
the plugin:

1. **At collection time** — parses the file's substrate headers via
   ``TestResolver.parse_test_header``, derives the rule-id from the
   acceptance URN per §3.3, and calls ``bind_rule()`` to verify the rule
   exists in the registry. The resulting ``RuleMetadata`` is stashed on the
   pytest item; tests whose acceptance was rejected by the walker
   (``RuleNotInRegistryError``) attach no metadata and run as plain pytest
   tests (the #410 conformance validators surface the upstream defect).

2. **At test-execution time** — intercepts the call-phase report via
   ``pytest_runtest_makereport``. When pytest classified the failure as an
   ``AssertionError`` (its existing crash-type-based logic does the
   lifting), constructs a structured ``Violation`` (rule_id from the
   binding, severity from the registry, location from the failure traceback,
   detail from the assertion message) and routes it through
   ``assert_disposition_satisfied`` with
   ``validator_id="<test_module>::<test_function>"``.

Non-``AssertionError`` failures (KeyError, fixture errors, collection
errors) surface as bare pytest errors — substrate enrichment is reserved
for the test author's contract claim, not environmental noise (spec v12
§7.2 final paragraph).

N-to-1 binding: each test anchored to the same acceptance is its own
pytest item; each item runs the interception independently. The shared
rule passes iff every sibling test passes (§4.5).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from atdd.coach.utils.disposition_gate import (
    assert_disposition_satisfied,
    record_rule_outcome,
    set_active_pytest_session,
)
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import (
    RepoYamlValidationError,
    RuleNotInRegistryError,
    bind_rule,
    derive_repo_rule_id,
)
from atdd.coach.utils.rule_id_registry import build_registry


_logger = logging.getLogger(__name__)


_HEADER_SCAN_BYTES = 8192
"""Read at most this many bytes when scanning a test file for headers.

The substrate's header block sits at the top of the file. Scanning the
whole module would cost N*M for N tests across M-line modules; the cap
mirrors the budget already used by ``TestResolver.parse_test_header``
callers and stays cache-friendly for large test suites.
"""

_ITEM_BINDING_KEY = "_atdd_substrate_binding"
"""Key under which we stash the per-item binding on the pytest Item."""

_DEFAULT_TEST_ROOT = "tests"
"""Spec v12 §7.2: fall back to ``tests/`` when neither config nor pyproject
declares a test root."""


# ---------------------------------------------------------------------------
# Test-root resolution (spec v12 §7.2 — order: .atdd config → pyproject → tests/)
# ---------------------------------------------------------------------------
def _resolve_test_roots(repo_root: Path) -> List[Path]:
    """Return absolute paths under ``repo_root`` to scan for anchored tests.

    Resolution order per spec:
      1. ``<repo>/.atdd/config.yaml::repo.test_root``
      2. ``<repo>/pyproject.toml::tool.pytest.ini_options.testpaths``
      3. ``<repo>/tests/`` (default)

    The substrate's ``atdd init --consumer-repo`` (#415) sets (1); pre-#415
    deployments fall back to (2) or (3). The plugin is permissive about
    missing/malformed config — collection-time hygiene is the conformance
    validator's job (#410), not the runner's.
    """
    candidates: List[Path] = []

    config_root = _read_atdd_config_test_root(repo_root)
    if config_root is not None:
        candidates.append(config_root)
    else:
        pyproject_roots = _read_pyproject_testpaths(repo_root)
        if pyproject_roots:
            candidates.extend(pyproject_roots)
        else:
            candidates.append(repo_root / _DEFAULT_TEST_ROOT)

    out: List[Path] = []
    seen: set = set()
    for c in candidates:
        absolute = c if c.is_absolute() else (repo_root / c)
        absolute = absolute.resolve()
        key = str(absolute)
        if key in seen:
            continue
        seen.add(key)
        if absolute.is_dir():
            out.append(absolute)
    return out


def _read_atdd_config_test_root(repo_root: Path) -> Optional[Path]:
    cfg = repo_root / ".atdd" / "config.yaml"
    if not cfg.is_file():
        return None
    try:
        import yaml

        with open(cfg, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        _logger.debug(
            "substrate plugin: skipping malformed %s: %s",
            cfg, exc,
            extra={"path": str(cfg), "error_type": type(exc).__name__},
        )
        return None
    if not isinstance(data, dict):
        return None
    repo_section = data.get("repo")
    if not isinstance(repo_section, dict):
        return None
    test_root = repo_section.get("test_root")
    if isinstance(test_root, str) and test_root.strip():
        return Path(test_root.strip())
    return None


def _read_pyproject_testpaths(repo_root: Path) -> List[Path]:
    pp = repo_root / "pyproject.toml"
    if not pp.is_file():
        return []
    try:
        try:
            import tomllib  # type: ignore[import-not-found]
        except ImportError:  # Python < 3.11
            import tomli as tomllib  # type: ignore[import-not-found]
        with open(pp, "rb") as fh:
            data = tomllib.load(fh)
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        _logger.debug(
            "substrate plugin: skipping malformed %s: %s",
            pp, exc,
            extra={"path": str(pp), "error_type": type(exc).__name__},
        )
        return []
    tool = data.get("tool") if isinstance(data, dict) else None
    pytest_section = tool.get("pytest") if isinstance(tool, dict) else None
    ini = pytest_section.get("ini_options") if isinstance(pytest_section, dict) else None
    if not isinstance(ini, dict):
        return []
    testpaths = ini.get("testpaths")
    if isinstance(testpaths, str):
        testpaths = [testpaths]
    if not isinstance(testpaths, list):
        return []
    out: List[Path] = []
    for tp in testpaths:
        if isinstance(tp, str) and tp.strip():
            out.append(Path(tp.strip()))
    return out


# ---------------------------------------------------------------------------
# Header-driven binding
# ---------------------------------------------------------------------------
def _read_header_text(test_file: Path) -> Optional[str]:
    try:
        with open(test_file, "r", encoding="utf-8") as fh:
            return fh.read(_HEADER_SCAN_BYTES)
    except (OSError, UnicodeDecodeError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        _logger.debug(
            "substrate plugin: cannot read %s: %s",
            test_file, exc,
            extra={"path": str(test_file), "error_type": type(exc).__name__},
        )
        return None


def _parse_acceptance_header(test_file: Path) -> Optional[str]:
    """Return the ``# Acceptance: <acc:URN>`` value declared in the file.

    Uses ``TestResolver.parse_test_header`` so the substrate sees the same
    header surface as every other consumer (single source of truth for
    header grammar). Returns ``None`` when no header is present.
    """
    text = _read_header_text(test_file)
    if text is None:
        return None
    # Late import — TestResolver ships in coach.utils.graph and importing
    # at module-load time would force the graph package to load on every
    # pytest invocation including ones that touch no anchored tests.
    from atdd.coach.utils.graph.resolver import TestResolver

    header = TestResolver.parse_test_header(text)
    acc = header.get("acceptance")
    if isinstance(acc, str) and acc.startswith("acc:"):
        return acc
    return None


def _bind_for_acceptance(acc_urn: str) -> Optional[Any]:
    """Look up the substrate rule for an acceptance URN.

    Returns the ``RuleMetadata`` from ``bind_rule`` on success, ``None``
    when:
      - the URN is malformed (``RepoYamlValidationError``);
      - the rule is not in the registry (``RuleNotInRegistryError``) —
        the walker rejected the upstream acceptance, so the plugin runs
        the test as a non-substrate pytest test and lets the #410
        validators surface the defect.
    """
    try:
        rule_id = derive_repo_rule_id(acc_urn)
    except RepoYamlValidationError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        # Malformed acc URN — the URN-grammar validator (#420) surfaces the
        # author defect at validation time. The plugin skips silently so a
        # bad header doesn't double-fail at runtime.
        _logger.debug(
            "substrate plugin: malformed acceptance URN %r: %s",
            acc_urn, exc,
            extra={"acceptance_urn": acc_urn, "error_type": type(exc).__name__},
        )
        return None
    try:
        return bind_rule(rule_id)
    except RuleNotInRegistryError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        # Walker rejected the upstream acceptance (missing phase, missing
        # measurability, etc.). Per spec §7.2 the test runs as a plain
        # pytest test; the #410 conformance validators surface the defect.
        _logger.debug(
            "substrate plugin: rule_id %r not in registry — running as plain test: %s",
            rule_id, exc,
            extra={"rule_id": rule_id, "error_type": type(exc).__name__},
        )
        return None
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        _logger.debug(
            "substrate plugin: bind_rule(%r) raised: %s",
            rule_id, exc,
            extra={"rule_id": rule_id, "error_type": type(exc).__name__},
        )
        return None


# ---------------------------------------------------------------------------
# Pytest hooks
# ---------------------------------------------------------------------------
_SECURITY_RUNNER_MODULE_STEM = "test_security_ref_binding"
_SECURITY_RUNTIME_TEST = "test_acceptance_ref_resolves_and_passes"


def pytest_configure(config: pytest.Config) -> None:
    """Register the substrate's custom marks so pytest doesn't warn.

    The substrate's pytest_collection_modifyitems hook applies
    ``atdd_phase("security")`` to security-runner items per spec v12
    §4.5. Without registration, pytest emits a ``PytestUnknownMarkWarning``
    on every test session — registering it here keeps the run quiet and
    documents the substrate-owned mark surface.
    """
    config.addinivalue_line(
        "markers",
        "atdd_phase(name): substrate phase tag; security-runner items "
        "are reordered after acceptance items per spec v12 §4.5.",
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    """Register the active session for the disposition gate.

    Substrate spec v12 §4.5 — the gate writes per-rule outcomes to
    ``session._atdd["rule_outcomes"]`` so the security runner can read
    them. The gate gets the session reference via
    ``set_active_pytest_session`` rather than threading it through every
    caller.
    """
    set_active_pytest_session(session)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Clear the active-session reference at session end.

    Avoids stale references between sequential pytest invocations in the
    same Python process (e.g. plugin tests, REPL workflows).
    """
    set_active_pytest_session(None)
    _NODEID_TO_RULE_ID.clear()


def pytest_collection_modifyitems(
    session: pytest.Session,
    config: pytest.Config,
    items: List[pytest.Item],
) -> None:
    """Attach substrate bindings + reorder security items after acceptance.

    Two concerns merge here so file paths cache once across the session:

      1. **Acceptance binding** (issue #411): for each anchored test
         (``# Acceptance: <acc:URN>`` header), derive the rule and stash
         the binding on the pytest item.
      2. **Security ordering** (issue #422 / spec v12 §4.5): apply
         ``@pytest.mark.atdd_phase("security")`` to the security runner's
         runtime test and reorder all security-marked items to run
         AFTER all acceptance-bound items in the same session. This
         guarantees the session result map (``_atdd["rule_outcomes"]``)
         is populated before the security runner reads it.
    """
    if not items:
        return

    repo_root = _detect_repo_root_for_session(session, config)
    test_roots = _resolve_test_roots(repo_root) if repo_root else []

    file_acc_cache: Dict[Path, Optional[str]] = {}
    rule_cache: Dict[str, Any] = {}

    for item in items:
        # Pass 1 — security mark application. The security runtime test
        # function lives in ``atdd.runners.test_security_ref_binding``;
        # apply the phase mark so the reorder pass below picks it up.
        # Idempotent: re-applying a mark with the same name is harmless.
        if _is_security_runtime_item(item):
            item.add_marker(pytest.mark.atdd_phase("security"))

        # Pass 2 — acceptance binding. Skipped when no test root resolved
        # (toolkit-only or weird checkout); harness mode just runs as
        # plain pytest in that case.
        if repo_root is None or not test_roots:
            continue

        path = _item_path(item)
        if path is None:
            continue
        if not _path_under_any_root(path, test_roots):
            continue

        if path not in file_acc_cache:
            file_acc_cache[path] = _parse_acceptance_header(path)
        acc = file_acc_cache[path]
        if acc is None:
            continue

        if acc not in rule_cache:
            rule_cache[acc] = _bind_for_acceptance(acc)
        rule = rule_cache[acc]
        if rule is None:
            continue

        validator_id = _validator_id_for_item(item)
        binding = {
            "rule_id": rule.rule_id,
            "severity": _severity_or_default(rule),
            "fix_hint_ref": getattr(rule, "fix_hint_ref", None),
            "acceptance_urn": acc,
            "validator_id": validator_id,
            "test_file": str(path),
        }
        setattr(item, _ITEM_BINDING_KEY, binding)
        # Mirror the binding into the module-level nodeid → rule_id map so
        # ``pytest_runtest_logreport`` (which only sees the report's
        # nodeid) can resolve the rule_id at outcome-record time.
        _NODEID_TO_RULE_ID[item.nodeid] = rule.rule_id

    # Pass 3 — stable-sort security-marked items after all others. We use
    # a stable sort with a binary key (0 = non-security, 1 = security)
    # so the rest of pytest's collection order is preserved.
    items.sort(key=_security_sort_key)


def _is_security_runtime_item(item: pytest.Item) -> bool:
    """Return True for the security runner's runtime pytest function.

    Identifies the item by its module stem + function name rather than by
    a string fixture path so the check works for both src-checkout and
    pip-installed deployments.
    """
    if item.name != _SECURITY_RUNTIME_TEST:
        return False
    path = _item_path(item)
    if path is None:
        return False
    return path.stem == _SECURITY_RUNNER_MODULE_STEM


def _has_security_phase_mark(item: pytest.Item) -> bool:
    """Return True when the item carries ``@pytest.mark.atdd_phase("security")``."""
    for mark in item.iter_markers(name="atdd_phase"):
        args = mark.args
        if args and args[0] == "security":
            return True
    return False


def _security_sort_key(item: pytest.Item) -> int:
    """Sort key — 1 for security-marked items, 0 for everything else."""
    return 1 if _has_security_phase_mark(item) else 0


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Record per-test outcomes for harness-anchored items (spec §4.5).

    Substrate spec v12 §4.5: the session result map
    (``session._atdd["rule_outcomes"]``) is populated by both the
    disposition gate (failure path) and the pytest plugin (pass path
    for harness mode). Failures already write through the gate; this
    hook records the pass-path entry so the security runner can
    distinguish "passed" from "did-not-run" rules.

    Only the ``call`` phase report is consulted — setup/teardown reports
    don't reflect the test author's contract claim.
    """
    if report.when != "call":
        return
    if report.outcome != "passed":
        # Failures already routed through the gate (which records "failed").
        # "skipped" outcomes are intentionally not recorded — a skipped
        # test exercised no contract; the security runner treats absence
        # as "did not run" rather than "passed".
        return

    rule_id = _rule_id_from_nodeid(report.nodeid)
    if rule_id is None:
        return

    record_rule_outcome(rule_id, "passed")


def _rule_id_from_nodeid(nodeid: str) -> Optional[str]:
    """Look up the harness-binding rule_id by pytest nodeid.

    Pytest reports carry only the nodeid string; the binding cache lives
    on the Item object (which the report does not reference). The binding
    cache below mirrors writes from ``pytest_collection_modifyitems`` so
    the logreport hook can resolve nodeid → rule_id without reaching back
    into the Item.
    """
    return _NODEID_TO_RULE_ID.get(nodeid)


# Per-session map populated alongside the per-Item binding stash. Cleared
# at session-end. Module-level rather than session-attached so the
# logreport hook can read it without holding the Session reference.
_NODEID_TO_RULE_ID: Dict[str, str] = {}


def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> None:
    """Intercept call-phase failures and route AssertionErrors through the gate.

    Uses ``pytest_runtest_makereport`` (after-call) instead of
    ``pytest_pyfunc_call`` (around-call) per spec v12 §7.2: it composes
    cleanly with other plugins and lets pytest's existing crash-type
    classification do the work.
    """
    if call.when != "call":
        return
    if call.excinfo is None:
        return

    binding = getattr(item, _ITEM_BINDING_KEY, None)
    if not binding:
        return

    excinfo = call.excinfo
    exc_type = excinfo.type
    if exc_type is None or not issubclass(exc_type, AssertionError):
        # Non-AssertionError failures (fixture errors, KeyError, etc.) are
        # environmental — they surface as bare pytest errors. The substrate
        # enriches the test author's contract claim, not infrastructure
        # noise (spec v12 §7.2).
        return

    if getattr(item, "_atdd_substrate_emitted", False):
        # Defensive: the same item should only be reported once per test
        # run. If two report hooks are wired (e.g. xdist re-emits), the
        # second pass should not trigger a second gate failure.
        return
    setattr(item, "_atdd_substrate_emitted", True)

    location = _format_location(item, excinfo, binding)
    detail = _format_detail(excinfo)

    from atdd.coach.validators._violation import Violation

    violation = Violation(
        rule_id=binding["rule_id"],
        severity=binding["severity"],
        location=location,
        detail=detail,
        fix_hint_ref=binding.get("fix_hint_ref"),
    )

    repo_root = _detect_repo_root_for_session(item.session, item.config)

    try:
        assert_disposition_satisfied(
            validator_id=binding["validator_id"],
            violations=[violation],
            registry=build_registry(repo_root=repo_root) if repo_root else None,
            repo_root=repo_root,
        )
    except pytest.fail.Exception as gate_failure:
        # The gate raised pytest.fail; rewrite the in-flight call's
        # excinfo so the per-test report carries the substrate-enriched
        # message instead of the bare AssertionError. The test still
        # fails (each anchored test runs independently), and the failure
        # block names the per-item validator_id.
        call.excinfo = pytest.ExceptionInfo.from_exception(gate_failure)
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        # If the gate machinery itself blows up, don't mask the original
        # AssertionError — surface a debug log and let pytest report the
        # real test failure as-is.
        _logger.warning(
            "substrate plugin: gate emission failed for %s: %s",
            binding.get("rule_id"), exc,
            extra={
                "rule_id": binding.get("rule_id"),
                "validator_id": binding.get("validator_id"),
                "error_type": type(exc).__name__,
            },
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _detect_repo_root_for_session(
    session: pytest.Session,
    config: pytest.Config,
) -> Optional[Path]:
    """Return the repo root for the active session, prefer rootpath then CWD.

    The substrate's ``find_repo_root`` walks parents looking for repo
    sentinels; pytest already computed the same kind of root at session
    setup. Either is fine — pytest's ``rootpath`` matches the user's
    invocation directory more closely so it wins when present.
    """
    candidates: List[Path] = []
    rootpath = getattr(config, "rootpath", None)
    if rootpath is not None:
        candidates.append(Path(rootpath))
    candidates.append(Path(os.getcwd()))

    for c in candidates:
        try:
            return find_repo_root(c.resolve())
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
            _logger.debug(
                "substrate plugin: find_repo_root(%s) raised: %s",
                c, exc,
                extra={"candidate": str(c), "error_type": type(exc).__name__},
            )
            continue
    return None


def _item_path(item: pytest.Item) -> Optional[Path]:
    """Return the absolute path of the test module for ``item``."""
    raw = getattr(item, "path", None)
    if raw is None:
        # pytest < 7 fallback
        fspath = getattr(item, "fspath", None)
        if fspath is None:
            return None
        try:
            return Path(str(fspath)).resolve()
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
            _logger.debug(
                "substrate plugin: cannot resolve item fspath %r: %s",
                fspath, exc,
                extra={"fspath": str(fspath), "error_type": type(exc).__name__},
            )
            return None
    try:
        return Path(str(raw)).resolve()
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        _logger.debug(
            "substrate plugin: cannot resolve item path %r: %s",
            raw, exc,
            extra={"path": str(raw), "error_type": type(exc).__name__},
        )
        return None


def _path_under_any_root(path: Path, roots: List[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _validator_id_for_item(item: pytest.Item) -> str:
    """Return ``"<module_basename>::<function_name>"`` per spec v12 §4.5.

    The basename strips ``.py`` so the substrate matches the ``validator:``
    contract used elsewhere in the toolkit (``RuleMetadata.validator``).
    Class-based tests render as ``<module>::<TestClass>::<method>`` so the
    full pytest nodeid path stays addressable.
    """
    path = _item_path(item)
    module = path.stem if path is not None else "unknown"
    name = item.name
    cls = getattr(item, "cls", None)
    if cls is not None and getattr(cls, "__name__", None):
        return f"{module}::{cls.__name__}::{name}"
    return f"{module}::{name}"


def _severity_or_default(rule: Any) -> int:
    severity = getattr(rule, "severity", None)
    if isinstance(severity, int) and not isinstance(severity, bool) and 1 <= severity <= 5:
        return severity
    # Spec §4.2 fixes acceptance-rule severity at 4. If the registry view
    # carries a non-int (legacy convention rule using "error"), default to
    # the substrate constant rather than crash construction of the
    # Violation.
    return 4


def _format_location(
    item: pytest.Item,
    excinfo: pytest.ExceptionInfo,
    binding: Dict[str, Any],
) -> str:
    """Format ``<test_file>:<lineno>`` for the failing assertion.

    Falls back to ``<test_file>:<test_function>`` when no traceback line
    is available — preserves spec v12 §6 sample output for train SMOKE
    tests where the location string carries the function name.
    """
    test_file = binding.get("test_file") or ""
    try:
        traceback = excinfo.traceback
        if traceback:
            entry = traceback[-1]
            lineno = getattr(entry, "lineno", None)
            if isinstance(lineno, int):
                # entry.lineno is 0-based on older pytest; +1 to render the
                # human line number consistent with `path:line` elsewhere.
                return f"{test_file}:{lineno + 1}"
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        _logger.debug(
            "substrate plugin: traceback parse failed, falling back to function name: %s",
            exc,
            extra={"error_type": type(exc).__name__},
        )
    return f"{test_file}:{item.name}"


def _format_detail(excinfo: pytest.ExceptionInfo) -> str:
    """Return the assertion's message (one line, defaulting to the type name)."""
    value = getattr(excinfo, "value", None)
    if value is None:
        return "AssertionError"
    text = str(value).strip()
    if not text:
        return "AssertionError"
    # Collapse multi-line assertion repr to a single line so the failure
    # block layout matches spec §6.
    first = next((line for line in text.splitlines() if line.strip()), text)
    return first


__all__ = [
    "pytest_collection_modifyitems",
    "pytest_configure",
    "pytest_runtest_logreport",
    "pytest_runtest_makereport",
    "pytest_sessionfinish",
    "pytest_sessionstart",
]
