# URN: component:govern-lifecycle:enforcement-substrate:test_state_store_invariants:backend:domain
# Runtime: python
# Purpose: Bind the State Store (#1168) architectural invariants to convention
#          nodes + node-graph validators (#1220) so the contracts are enforced
#          rules surfaced in `atdd validate`, not ad-hoc GREEN tests.

"""State Store invariant validators (issue #1220).

The State Store (#1168) shipped with comprehensive GREEN tests but no
rule-bound validators — its core contracts could silently regress. This
module binds five invariants to convention nodes under the ``coder.state-store``
namespace; each test routes through ``assert_disposition_satisfied`` so a
breach fails CI at the rule's declared ``strict`` disposition.

Invariants:

1. ``coder.state-store.core-imports-no-providers`` — ``atdd.state`` is a
   foundational layer and must not import ``atdd.coach``/``train``/
   ``integrations``/``runtime``/``observer``. (Migrated from the interim
   ``tests/architecture/test_layer_imports.py`` ``atdd.state`` gate line.)
2. ``coder.state-store.sync-engine-provider-agnostic`` — ``sync_engine.py``
   must name no concrete provider ("github", etc.); providers plug in behind
   the SyncProvider seam (#1201).
3. ``coder.state-store.no-raw-sql-at-call-sites`` — outside ``atdd.state``,
   no module may import ``sqlite3`` directly; persistence goes through the
   storage APIs.
4. ``coder.state-store.one-external-ref-per-issue`` — the ``external_refs``
   schema must declare ``UNIQUE (provider, ref_kind, ref_value)`` so one
   provider ref maps to exactly one work item (the import-collision rule).
5. ``coder.state-store.single-store-per-control-root`` — the ``check_layout``
   single-store guard must exist, be invoked by the CLI (``doctor`` /
   ``layout``), AND actually bite: a behavioral probe (#1346) requires it to
   report a violation for a synthetic rogue per-worktree store, so a
   defined-but-toothless guard cannot pass. Sibling-worktree mode allows exactly
   one store.
6. ``coder.state-store.work-item-provenance`` (#1557) — every ``work_item`` in
   the live store has a sanctioned authoring event as its FIRST event. Unlike
   invariants 1–4, which scan source text, this one reads the running store
   (``objects`` + ``events``), because the fault it catches is a *record*
   created outside the sanctioned path — something no amount of source reading
   can see. It names no provider and makes no network call, and it **fails
   closed**: an unreadable store raises out of the test rather than passing
   vacuously, which is why that path deliberately bypasses the disposition gate.

Convention nodes: ``src/atdd/coder/conventions/nodes/coder.state-store.*.convention.yaml``.
"""

from __future__ import annotations

import ast
import re
import tempfile
from pathlib import Path
from typing import List, Optional

import pytest

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied


# ---------------------------------------------------------------------------
# Rule bindings — fail at import if the convention nodes drift.
# ---------------------------------------------------------------------------
_RULE_LAYER = bind_rule("coder.state-store.core-imports-no-providers")
_RULE_SYNC = bind_rule("coder.state-store.sync-engine-provider-agnostic")
_RULE_SQL = bind_rule("coder.state-store.no-raw-sql-at-call-sites")
_RULE_REF = bind_rule("coder.state-store.one-external-ref-per-issue")
_RULE_STORE = bind_rule("coder.state-store.single-store-per-control-root")
_RULE_PROVENANCE = bind_rule("coder.state-store.work-item-provenance")


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
REPO_ROOT = find_repo_root()
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
STATE_DIR = ATDD_PKG_DIR / "state"

# The forbidden inward set for the foundational State Store layer. Mirrors
# ``FORBIDDEN_BY_LAYER["atdd.state"]`` in tests/architecture/test_layer_imports.py,
# whose enforcement this validator supersedes (issue #1220).
_FORBIDDEN_LAYER_IMPORTS = (
    "atdd.coach",
    "atdd.train",
    "atdd.integrations",
    "atdd.runtime",
)

# Concrete provider names the agnostic sync engine must not reference.
_PROVIDER_NAMES = frozenset(
    {"github", "gitlab", "bitbucket", "gitea", "jira", "linear", "azure"}
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _relpath(p: Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def _iter_py(root: Path) -> List[Path]:
    """Source ``.py`` files under *root*, excluding tests and __pycache__."""
    out: List[Path] = []
    if not root.is_dir():
        return out
    for py in root.rglob("*.py"):
        parts = set(py.parts)
        if "__pycache__" in parts or "tests" in parts or "fixtures" in parts:
            continue
        if py.name.startswith("test_"):
            continue
        out.append(py)
    return out


def _module_imports(tree: ast.AST) -> List[tuple[str, int]]:
    """Return ``(module, lineno)`` for every import in *tree*."""
    out: List[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                out.append((n.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.append((node.module, node.lineno))
    return out


# ---------------------------------------------------------------------------
# Scanners
# ---------------------------------------------------------------------------
def scan_core_imports_no_providers() -> List[Violation]:
    """Invariant 1: ``atdd.state`` imports no upper-layer package."""
    violations: List[Violation] = []
    for py in _iter_py(STATE_DIR):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for module, lineno in _module_imports(tree):
            for fb in _FORBIDDEN_LAYER_IMPORTS:
                if module == fb or module.startswith(fb + "."):
                    violations.append(
                        Violation(
                            rule_id=_RULE_LAYER.rule_id,
                            severity=_RULE_LAYER.severity,
                            location=f"{_relpath(py)}:{lineno}",
                            detail=(
                                f"foundational layer atdd.state imports {module!r} "
                                f"(forbidden inward dependency on {fb})"
                            ),
                        )
                    )
                    break
    return violations


def scan_sync_engine_provider_agnostic() -> List[Violation]:
    """Invariant 2: ``sync_engine.py`` names no concrete provider."""
    sync_engine = STATE_DIR / "sync_engine.py"
    if not sync_engine.is_file():
        return [
            Violation(
                rule_id=_RULE_SYNC.rule_id,
                severity=_RULE_SYNC.severity,
                location=f"{_relpath(sync_engine)}:1",
                detail="sync_engine.py is missing — the provider-agnostic engine seam is gone",
            )
        ]
    violations: List[Violation] = []
    tree = ast.parse(sync_engine.read_text(encoding="utf-8"), filename=str(sync_engine))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.strip().lower() in _PROVIDER_NAMES:
                violations.append(
                    Violation(
                        rule_id=_RULE_SYNC.rule_id,
                        severity=_RULE_SYNC.severity,
                        location=f"{_relpath(sync_engine)}:{node.lineno}",
                        detail=(
                            f"sync engine references concrete provider {node.value.strip()!r}; "
                            "providers must plug in behind the SyncProvider seam"
                        ),
                    )
                )
    return violations


def scan_no_raw_sql_outside_state() -> List[Violation]:
    """Invariant 3: no module outside ``atdd.state`` imports sqlite3 directly."""
    violations: List[Violation] = []
    for py in _iter_py(ATDD_PKG_DIR):
        if STATE_DIR in py.parents or py == STATE_DIR:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for module, lineno in _module_imports(tree):
            if module == "sqlite3" or module.startswith("sqlite3."):
                violations.append(
                    Violation(
                        rule_id=_RULE_SQL.rule_id,
                        severity=_RULE_SQL.severity,
                        location=f"{_relpath(py)}:{lineno}",
                        detail=(
                            "direct sqlite3 import outside atdd.state; persistence "
                            "must go through the State Store storage APIs"
                        ),
                    )
                )
    return violations


_EXTERNAL_REFS_UNIQUE_RE = re.compile(
    r"UNIQUE\s*\(\s*provider\s*,\s*ref_kind\s*,\s*ref_value\s*\)",
    re.IGNORECASE,
)


def scan_one_external_ref_per_issue() -> List[Violation]:
    """Invariant 4: external_refs schema enforces ref uniqueness structurally."""
    migrations = STATE_DIR / "migrations.py"
    if not migrations.is_file():
        return [
            Violation(
                rule_id=_RULE_REF.rule_id,
                severity=_RULE_REF.severity,
                location=f"{_relpath(migrations)}:1",
                detail="state/migrations.py is missing — cannot verify the external_refs uniqueness constraint",
            )
        ]
    text = migrations.read_text(encoding="utf-8")
    if _EXTERNAL_REFS_UNIQUE_RE.search(text):
        return []
    return [
        Violation(
            rule_id=_RULE_REF.rule_id,
            severity=_RULE_REF.severity,
            location=f"{_relpath(migrations)}:1",
            detail=(
                "external_refs schema must declare UNIQUE (provider, ref_kind, ref_value) "
                "so one provider ref maps to exactly one work item"
            ),
        )
    ]


def scan_single_store_per_control_root() -> List[Violation]:
    """Invariant 5: the check_layout single-store guard exists and is CLI-wired."""
    paths_py = STATE_DIR / "paths.py"
    cli_py = STATE_DIR / "cli.py"
    violations: List[Violation] = []

    defined = paths_py.is_file() and "def check_layout(" in paths_py.read_text(
        encoding="utf-8"
    )
    if not defined:
        violations.append(
            Violation(
                rule_id=_RULE_STORE.rule_id,
                severity=_RULE_STORE.severity,
                location=f"{_relpath(paths_py)}:1",
                detail="check_layout single-store guard is not defined in state/paths.py",
            )
        )

    cli_text = cli_py.read_text(encoding="utf-8") if cli_py.is_file() else ""
    # Call-sites only (exclude the import statement).
    call_sites = sum(
        1
        for line in cli_text.splitlines()
        if "check_layout(" in line and not line.lstrip().startswith(("from ", "import "))
    )
    if call_sites < 1:
        violations.append(
            Violation(
                rule_id=_RULE_STORE.rule_id,
                severity=_RULE_STORE.severity,
                location=f"{_relpath(cli_py)}:1",
                detail=(
                    "check_layout is not invoked by the state CLI (doctor/layout); "
                    "the single-store-per-control-root guard is unwired"
                ),
            )
        )

    # Behavioral probe (#1346): the guard must actually BITE, not merely be
    # defined and CLI-referenced. Build a synthetic rogue layout (a Control Root
    # whose child worktree carries its own state.sqlite) and require check_layout
    # to report it. A defined-but-toothless guard (returns [] here) fails the
    # invariant — this is what lifts #1220 from a wiring grep to an observed
    # single-store contract. Resolved through the module so a neutered guard is
    # caught even if the symbol is monkeypatched.
    from atdd.state import paths as _paths  # local: state is a lower foundational layer

    with tempfile.TemporaryDirectory() as _tmp:
        _root = Path(_tmp)
        (_root / ".atdd").mkdir()  # control root marker
        _child = _root / "wt1"
        (_child / ".git").mkdir(parents=True)
        _rogue = _child / ".atdd" / "state" / "state.sqlite"
        _rogue.parent.mkdir(parents=True)
        _rogue.touch()
        if not _paths.check_layout(_root):
            violations.append(
                Violation(
                    rule_id=_RULE_STORE.rule_id,
                    severity=_RULE_STORE.severity,
                    location=f"{_relpath(paths_py)}:1",
                    detail=(
                        "check_layout is toothless — it reported no violation for a "
                        "rogue per-worktree State Store below the Control Root; the "
                        "single-store-per-control-root guard does not bite"
                    ),
                )
            )
    return violations


def scan_work_item_provenance(control_root: Optional[Path] = None) -> List[Violation]:
    """Invariant 6 (#1557): every ``work_item``'s first event is sanctioned.

    Reads the live State Store — ``objects`` + ``events`` — through the storage
    APIs. No provider is imported, named or called anywhere on this path; the
    whole point of the design is that the answer comes from the record.

    FAILS CLOSED — but on the right boundary. "Fail closed" means *an existing
    store I cannot read must not read as clean*. It does NOT mean "any tree
    without a store fails", and the difference is the whole correctness of the
    rule:

    - **No Control Root** (a consumer repo that has never run ``atdd init``, or
      any checkout of this package installed as a dependency): there is no
      store, therefore no ``work_item``, therefore no record whose provenance
      could be laundered. The invariant has no subject here and the scan is
      vacuously clean. Raising instead would fail every consumer of the shipped
      wheel over a store they were never supposed to have.
    - **Control Root but no store file yet**: same — the store is created on
      first write, and a store that has never been written holds no records.
    - **Store present but unopenable/unqueryable**: RAISES
      :class:`~atdd.state.provenance.ProvenanceStoreUnreadable`. This is the
      case the fail-closed property exists for. Returning ``[]`` here would be
      indistinguishable from "everything is fine".

    Note the asymmetry that keeps this honest: a *finding* is subject to the
    rule's declared disposition (advisory today), but an unreadable store is not
    a finding — no disposition tier can downgrade it.

    Deliberately resolves the Control Root rather than calling
    ``init_state_store``: a validator must not CREATE a store as a side effect of
    checking one.
    """
    from atdd.state import provenance  # local: state is a lower foundational layer
    from atdd.state.db import connect
    from atdd.state.paths import ControlRootNotFoundError, resolve_control_root

    start = control_root or REPO_ROOT
    try:
        resolution = resolve_control_root(Path(start))
    except ControlRootNotFoundError:
        return []  # no Control Root ⇒ no store ⇒ no records ⇒ nothing to check

    if not resolution.state_store_exists:
        return []  # never written ⇒ holds no records

    try:
        conn = connect(resolution.state_store_path)
    except Exception as exc:  # noqa: BLE001 — a store that EXISTS must be readable
        raise provenance.ProvenanceStoreUnreadable(
            f"State Store at {resolution.state_store_path} exists but could not be "
            f"opened; provenance could not be evaluated: {exc}"
        ) from exc

    try:
        findings = provenance.audit_work_items(conn)
    finally:
        conn.close()

    return [
        Violation(
            rule_id=_RULE_PROVENANCE.rule_id,
            severity=_RULE_PROVENANCE.severity,
            location=f"state:work_item/{f.uid}",
            detail=f.detail,
        )
        for f in findings
    ]


# ===========================================================================
# Tests — one per invariant, routed through the disposition gate.
# ===========================================================================
@pytest.mark.coder
def test_state_core_imports_no_providers():
    """SPEC: ``coder.state-store.core-imports-no-providers``.

    Given: Python modules under ``src/atdd/state/``.
    When:  Their imports are AST-extracted.
    Then:  None imports atdd.coach/train/integrations/runtime/observer.
    """
    assert_disposition_satisfied(
        validator_id="state_store_core_imports_no_providers",
        violations=scan_core_imports_no_providers(),
    )


@pytest.mark.coder
def test_sync_engine_provider_agnostic():
    """SPEC: ``coder.state-store.sync-engine-provider-agnostic``.

    Given: ``src/atdd/state/sync_engine.py``.
    When:  String literals are scanned.
    Then:  None equals a concrete provider name.
    """
    assert_disposition_satisfied(
        validator_id="state_store_sync_engine_provider_agnostic",
        violations=scan_sync_engine_provider_agnostic(),
    )


@pytest.mark.coder
def test_no_raw_sql_outside_state():
    """SPEC: ``coder.state-store.no-raw-sql-at-call-sites``.

    Given: Python modules under ``src/atdd/`` outside ``state/``.
    When:  Their imports are AST-extracted.
    Then:  None imports sqlite3 directly.
    """
    assert_disposition_satisfied(
        validator_id="state_store_no_raw_sql_outside_state",
        violations=scan_no_raw_sql_outside_state(),
    )


@pytest.mark.coder
def test_one_external_ref_per_issue():
    """SPEC: ``coder.state-store.one-external-ref-per-issue``.

    Given: ``src/atdd/state/migrations.py``.
    When:  The external_refs schema is inspected.
    Then:  It declares UNIQUE (provider, ref_kind, ref_value).
    """
    assert_disposition_satisfied(
        validator_id="state_store_one_external_ref_per_issue",
        violations=scan_one_external_ref_per_issue(),
    )


@pytest.mark.coder
def test_single_store_per_control_root():
    """SPEC: ``coder.state-store.single-store-per-control-root``.

    Given: ``src/atdd/state/paths.py`` and ``cli.py``.
    When:  The check_layout guard's definition and CLI wiring are inspected.
    Then:  The guard is defined and invoked by the CLI.
    """
    assert_disposition_satisfied(
        validator_id="state_store_single_store_per_control_root",
        violations=scan_single_store_per_control_root(),
    )


@pytest.mark.coder
@pytest.mark.live_store_read  # sanctioned live-corpus reader (#1582)
def test_work_item_provenance():
    """SPEC: ``coder.state-store.work-item-provenance``.

    Marked ``live_store_read`` because this validator audits the REAL store by
    design — that is the whole point of a live-corpus scan, and pointing it at a
    tmp_path would make it assert nothing. The #1582 write guard permits the
    open for marked tests only; its fingerprint backstop still runs here, so
    "this scan only reads" is proved rather than trusted.

    Given: The live State Store's ``objects`` and ``events`` tables.
    When:  Each ``work_item``'s lowest-seq event is read.
    Then:  It is a sanctioned authoring event.

    An unreadable store propagates ``ProvenanceStoreUnreadable`` and errors the
    run — it is not routed through the disposition gate, because the gate
    decides what to do with *findings*, and "I could not look" is not a finding.
    """
    assert_disposition_satisfied(
        validator_id="state_store_work_item_provenance",
        violations=scan_work_item_provenance(),
    )
