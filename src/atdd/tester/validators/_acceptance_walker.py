# URN: component:govern-lifecycle:enforcement-substrate:_acceptance_walker:backend:domain
# Runtime: python
# Purpose: Shared helper for substrate enforcement validators (#410) — walks plan/ for raw acceptance blocks without applying the registry walker's silent skips.

"""Raw plan/ walker for the Track-B substrate enforcement validators.

The registry walker in ``atdd.coach.utils.rule_binding.find_repo_rules``
SILENTLY SKIPS acceptances that fail the §4.3 invariants (missing phase,
missing harness+signal). That keeps the registry clean — but it means
the substrate enforcement validators cannot consume the registry to
surface those very failures (they would never see the broken
acceptances in the first place).

This module walks the same files raw: it reads each WMBT and train YAML
under ``plan/`` and yields every ``acceptances[]`` block it finds,
regardless of whether the block satisfies the walker invariants. The
validators then check each invariant themselves and emit ``Violation``
records keyed off the conformance rule_ids defined in
``acceptance-violation.convention.yaml``.
"""

from __future__ import annotations

import logging
import os
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import yaml

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.validators._violation import Violation


_logger = logging.getLogger(__name__)


SUBSTRATE_BACKLOG_ENV = "ATDD_ALLOW_SUBSTRATE_BACKLOG"
"""Emergency opt-out env var for the five Track-B conformance validators.

When set to a truthy value, ``assert_substrate_strict`` demotes every
substrate-conformance violation to a ``UserWarning`` instead of failing.

Use case: substrate ships strict-from-day-1 (spec §11), but each
consuming repo (including this toolkit's own ``plan/``) must clear its
Class-1 backlog (#410's siblings — #413 metric impl, #422 abuse-case
binding, etc.) before the conformance suite is allowed to gate CI. The
env var is the same shape as ``ATDD_ALLOW_ORPHAN_RULES`` (issue #399)
and is meant to be removed from CI once backlog is clear.
"""


_WMBT_FILE_RE = re.compile(r"^[DLPCEMYRK]\d{3}\.yaml$")


@dataclass(frozen=True)
class RawAcceptance:
    """One acceptances[] entry as it appears in the source YAML.

    Attributes:
        file: Absolute path to the YAML file containing the block.
        kind: ``"wmbt"`` for WMBT files, ``"train"`` for train files.
        index: Zero-based position inside the file's ``acceptances:`` list.
        body: The raw acceptance dict (may be ill-formed — that's the point).
        location: ``"<relpath>:acceptances[<index>]"`` for Violation.location.
    """

    file: Path
    kind: str
    index: int
    body: dict
    location: str


def iter_repo_acceptances(repo_root: Path) -> Iterator[RawAcceptance]:
    """Yield every ``acceptances[]`` entry under ``<repo>/plan/``.

    Reads:
      - ``plan/<wagon>/[DLPCEMYRK]NNN.yaml``  (WMBT acceptances).
      - ``plan/_trains/**/*.yaml``            (train acceptances).

    The train walk RECURSES (#1548). Typed trains (#1421) live nested at
    ``plan/_trains/<subject>/<slug>.yaml``; the original top-level-only glob
    saw none of them, so every train acceptance in the repo was invisible to
    the substrate validators — the forward pass never required a test, and the
    reverse pass read any test anchored to one as an orphan. Underscore-
    prefixed subdirectories (``_interlockings``) are registry/control
    artifacts, not trains, and are skipped like the wagon loop skips them.

    Files that fail to parse, or whose top level is not a dict with an
    ``acceptances:`` list, are silently skipped — those are caught by
    other validators (URN graph, schema validation). The caller checks
    invariants on the raw body.
    """
    plan_dir = (repo_root / "plan").resolve()
    if not plan_dir.is_dir():
        return

    for wagon_dir in sorted(plan_dir.iterdir()):
        if not wagon_dir.is_dir() or wagon_dir.name.startswith("_"):
            continue
        for wmbt_file in sorted(wagon_dir.glob("*.yaml")):
            if not _WMBT_FILE_RE.match(wmbt_file.name):
                continue
            yield from _iter_acceptances_in_file(wmbt_file, "wmbt", repo_root)

    trains_dir = plan_dir / "_trains"
    if trains_dir.is_dir():
        for train_file in sorted(_iter_train_files(trains_dir)):
            yield from _iter_acceptances_in_file(train_file, "train", repo_root)


def _iter_train_files(trains_dir: Path) -> Iterator[Path]:
    """Yield every train YAML under ``plan/_trains/``, flat or subject-nested.

    Legacy trains sit flat (``0007-enforce-extension-conventions.yaml``); typed
    trains (#1421) sit one level down under their subject
    (``self-compliance/validate-lifecycle.yaml``). Underscore-prefixed names are
    registries (``_trains.yaml``, ``_aliases.yaml``) or control artifacts
    (``_interlockings/``), never trains.
    """
    for path in trains_dir.rglob("*.yaml"):
        if any(part.startswith("_") for part in path.relative_to(trains_dir).parts):
            continue
        yield path


def _iter_acceptances_in_file(
    path: Path, kind: str, repo_root: Path
) -> Iterator[RawAcceptance]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        # Malformed plan/ YAMLs are policed by URN-graph validators; this
        # walker treats them as empty so a single broken file doesn't mask
        # other conformance failures across the rest of plan/.
        _logger.debug(
            "_acceptance_walker: skipping unreadable %s: %s",
            path, exc,
            extra={"path": str(path), "error_type": type(exc).__name__},
        )
        return
    if not isinstance(data, dict):
        return
    acceptances = data.get("acceptances")
    if not isinstance(acceptances, list):
        return

    rel_path = _relpath(path, repo_root)
    for idx, body in enumerate(acceptances):
        if not isinstance(body, dict):
            continue
        yield RawAcceptance(
            file=path.resolve(),
            kind=kind,
            index=idx,
            body=body,
            location=f"{rel_path}:acceptances[{idx}]",
        )


def iter_repo_wmbts(repo_root: Path) -> Iterator[Tuple[Path, dict]]:
    """Yield ``(path, wmbt_dict)`` for every WMBT file under ``plan/<wagon>/``.

    Unlike :func:`iter_repo_acceptances` (which flattens to individual
    ``acceptances[]`` entries), this preserves the WMBT-level grouping so
    callers can reason about sibling acceptances under the same parent WMBT
    (e.g. live-smoke pairing, issue #690).

    Files that fail to parse, or whose top level is not a dict, are silently
    skipped — those are policed by the URN-graph validators.
    """
    plan_dir = (repo_root / "plan").resolve()
    if not plan_dir.is_dir():
        return
    for wagon_dir in sorted(plan_dir.iterdir()):
        if not wagon_dir.is_dir() or wagon_dir.name.startswith("_"):
            continue
        for wmbt_file in sorted(wagon_dir.glob("*.yaml")):
            if not _WMBT_FILE_RE.match(wmbt_file.name):
                continue
            try:
                data = yaml.safe_load(wmbt_file.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
                # Malformed plan/ YAML is policed by the URN-graph validators.
                _logger.debug(
                    "_acceptance_walker: skipping unreadable %s: %s",
                    wmbt_file, exc,
                    extra={"path": str(wmbt_file), "error_type": type(exc).__name__},
                )
                continue
            if isinstance(data, dict):
                yield wmbt_file, data


def iter_feature_files(repo_root: Path) -> Iterator[Path]:
    """Yield ``feature.yaml`` files under ``plan/<wagon>/`` (substrate spec §3.2)."""
    plan_dir = (repo_root / "plan").resolve()
    if not plan_dir.is_dir():
        return
    for wagon_dir in sorted(plan_dir.iterdir()):
        if not wagon_dir.is_dir() or wagon_dir.name.startswith("_"):
            continue
        for candidate in sorted(wagon_dir.glob("*.yaml")):
            if candidate.name in {"feature.yaml", "_feature.yaml"}:
                yield candidate


def acceptance_urn(body: dict) -> Optional[str]:
    """Pull ``identity.urn`` from a raw acceptance body, or None."""
    identity = body.get("identity") if isinstance(body, dict) else None
    if not isinstance(identity, dict):
        return None
    urn = identity.get("urn")
    return urn if isinstance(urn, str) and urn else None


def acceptance_phase(body: dict) -> Optional[str]:
    """Pull ``identity.phase`` from a raw acceptance body, or None."""
    identity = body.get("identity") if isinstance(body, dict) else None
    if not isinstance(identity, dict):
        return None
    phase = identity.get("phase")
    return phase if isinstance(phase, str) and phase else None


def has_harness_type(body: dict) -> bool:
    """True iff ``harness.type`` is present and a non-empty string."""
    harness = body.get("harness") if isinstance(body, dict) else None
    if not isinstance(harness, dict):
        return False
    t = harness.get("type")
    return isinstance(t, str) and bool(t)


def has_signal_metric_and_threshold(body: dict) -> bool:
    """True iff BOTH ``signal.metric`` and ``signal.threshold`` are populated."""
    signal = body.get("signal") if isinstance(body, dict) else None
    if not isinstance(signal, dict):
        return False
    metric = signal.get("metric")
    if not isinstance(metric, str) or not metric:
        return False
    return signal.get("threshold") is not None


def find_disposition_path(node, parts=()) -> Optional[tuple]:
    """Return the YAML path tuple to the first ``disposition:`` key, else None.

    Mirrors ``rule_binding._find_disposition_anywhere`` so the substrate
    enforcement validator surfaces the same field the walker rejects.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "disposition":
                return parts + (key,)
            sub = find_disposition_path(value, parts + (key,))
            if sub is not None:
                return sub
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            sub = find_disposition_path(item, parts + (idx,))
            if sub is not None:
                return sub
    return None


def yaml_path_str(parts) -> str:
    """Render a YAML key-path tuple as a dotted string for Violation.detail."""
    return ".".join(str(p) for p in parts) if parts else "<root>"


def _relpath(path: Path, repo_root: Path) -> str:
    """Best-effort relative path; falls back to absolute when outside the root."""
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow)
        # Path outside repo_root (e.g., absolute fixture path under tmp).
        # Falling back to the absolute string is the documented behavior
        # — the caller uses the result purely for Violation.location, not
        # for reading the file again.
        return str(path)


def assert_substrate_strict(
    validator_id: str,
    violations: Sequence[Violation],
) -> None:
    """Strict-by-default gate for substrate Track-B conformance validators.

    Default behavior: hands the violations to
    ``assert_disposition_satisfied`` — the convention sets
    ``disposition: strict`` so any violation fails the test.

    Emergency opt-out: when ``ATDD_ALLOW_SUBSTRATE_BACKLOG`` is set to a
    truthy value, the violations are demoted to a ``UserWarning`` and
    the test passes. The env var is intended for the migration window
    while Class-1 backlog (missing metric impls, missing test files for
    pre-existing acceptances) is cleared by the substrate's sibling
    issues. Remove the env var from CI once backlog is at zero.
    """
    if not violations:
        return
    if _is_truthy_env(os.environ.get(SUBSTRATE_BACKLOG_ENV)):
        warnings.warn(
            f"[{SUBSTRATE_BACKLOG_ENV}] {validator_id}: "
            f"substrate conformance found {len(violations)} violation(s); "
            f"gate demoted to WARN. Sample:\n  - "
            + "\n  - ".join(
                f"{v.rule_id}: {v.location}: {v.detail}"
                for v in list(violations)[:5]
            ),
            UserWarning,
            stacklevel=2,
        )
        return
    assert_disposition_satisfied(validator_id, violations)


def _is_truthy_env(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() not in {"", "0", "false", "no", "off"}


_ACCEPTANCE_HEADER_RE = re.compile(r"(?:#|//)\s*[Aa]cceptance:\s*(acc:[^\s]+)")
_TEST_FILENAME_RE = re.compile(
    r"^(?:test_.*\.py|.*_test\.py|.*\.test\.tsx?|.*\.spec\.ts|.*_test\.dart)$"
)
_TEST_EXTS = {".py", ".ts", ".tsx", ".dart"}
_PRUNE_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".tox",
    ".pytest_cache",
    ".mypy_cache",
    "site-packages",
}


def scan_test_acceptance_headers(repo_root: Path) -> Dict[str, List[Path]]:
    """Return ``{acceptance_urn: [test_file, ...]}`` for every anchored test.

    Walks the repo for test files (pruning vendored/build dirs) and reads the
    leading comment block of each for ``# Acceptance: acc:...`` headers. Shared
    by the substrate enforcement validators that bind acceptances to their
    anchored tests (e.g. validator-binding, live-smoke-execution) so the scan
    lives in one place.
    """
    index: Dict[str, List[Path]] = {}
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in _PRUNE_DIRS]
        for fname in filenames:
            ext = "." + fname.rsplit(".", 1)[-1] if "." in fname else ""
            if ext.lower() not in _TEST_EXTS or not _TEST_FILENAME_RE.match(fname):
                continue
            test_file = Path(dirpath) / fname
            try:
                text = test_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            # Only the leading comment block — avoids false positives from
            # prose mentioning "# Acceptance: acc:..." inside a test body/string.
            head = "\n".join(text.split("\n", 30)[:30])
            for match in _ACCEPTANCE_HEADER_RE.finditer(head):
                index.setdefault(match.group(1).strip(), []).append(test_file)
    return index


# ---------------------------------------------------------------------------
# Owning-issue phase resolution (issue #1242)
#
# The repo-wide binding validator's forward pass must not demand an anchored
# test before the OWNING ISSUE has reached the phase at which the test is due
# (RED). The issue's current phase is read from ``.atdd/manifest.yaml``
# ``sessions[]`` — the authoritative source the #1168 State Store imports —
# keyed by wagon. The linear phase order is sourced from
# ``phase_machine.convention.yaml`` so no second phase ordering is forked.
# ---------------------------------------------------------------------------

_PHASE_MACHINE_PATH = (
    Path(__file__).resolve().parents[2]
    / "coach" / "conventions" / "phase_machine.convention.yaml"
)

# The phase at which an acceptance's anchored test becomes due. Strictly before
# it (INIT, PLANNED) the test is legitimately not yet authored.
_TEST_DUE_PHASE = "RED"

_LINEAR_PHASE_FALLBACK = ["INIT", "PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR", "COMPLETE"]


def _linear_phase_order() -> List[str]:
    """Canonical linear lifecycle phases, in order, from the phase machine.

    Walks ``phase_machine.convention.yaml`` from INIT following each phase's
    first ``transitions_to`` entry (the forward/happy-path target; the rest are
    the BLOCKED/OBSOLETE escapes), yielding
    ``[INIT, PLANNED, RED, GREEN, SMOKE, REFACTOR, COMPLETE]``. Returns a safe
    hardcoded fallback if the convention is unreadable.
    """
    try:
        data = yaml.safe_load(_PHASE_MACHINE_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):  # atdd:suppress(coder.logging.coach-silent-swallow)
        # Phase order is a toolkit constant; an unreadable convention falls back
        # to the documented linear order rather than masking the comparison.
        return list(_LINEAR_PHASE_FALLBACK)
    phases = data.get("phases") if isinstance(data, dict) else None
    if not isinstance(phases, dict) or "INIT" not in phases:
        return list(_LINEAR_PHASE_FALLBACK)
    order: List[str] = []
    seen: set = set()
    cur: Optional[str] = "INIT"
    while cur and cur not in seen:
        order.append(cur)
        seen.add(cur)
        spec = phases.get(cur) or {}
        nxt = spec.get("transitions_to") if isinstance(spec, dict) else None
        cur = nxt[0] if isinstance(nxt, list) and nxt else None
    return order or list(_LINEAR_PHASE_FALLBACK)


def is_pre_test_phase(phase: Optional[str]) -> bool:
    """True iff *phase* is strictly before RED in the lifecycle (test not due).

    INIT and PLANNED return True. RED, GREEN, SMOKE, REFACTOR, COMPLETE and any
    unknown/escape token (BLOCKED, OBSOLETE, None, '') return False — fail-closed,
    so an unrecognized phase always *requires* the anchored test.
    """
    if not isinstance(phase, str) or not phase:
        return False
    order = _linear_phase_order()
    if phase not in order or _TEST_DUE_PHASE not in order:
        return False
    return order.index(phase) < order.index(_TEST_DUE_PHASE)


def _acceptance_wagon(acc: RawAcceptance) -> Optional[str]:
    """Best-effort wagon slug owning *acc*.

    Prefers the acceptance URN's wagon segment (``acc:<wagon>:…``); falls back
    to the ``plan/<wagon_dir>/`` parent (underscores → hyphens). Train-level
    acceptances (under ``plan/_trains/``) resolve via their URN segment, which
    is matched against ``sessions[].train`` by the caller.
    """
    urn = acceptance_urn(acc.body)
    if urn and urn.startswith("acc:"):
        parts = urn.split(":")
        if len(parts) >= 2 and parts[1]:
            return parts[1]
    parent = acc.file.parent.name
    if parent and not parent.startswith("_"):
        return parent.replace("_", "-")
    return None


def _store_work_items(repo_root: Path) -> List[dict]:
    """All work items as session-shaped dicts from the State Store (#1270 slice E).

    Replaces the ``.atdd/manifest.yaml`` ``sessions[]`` read: the store is
    authoritative (#1203) and additionally carries issues created store-first
    (which the manifest never tracked, so the old read could not see them).
    Returns an empty list on any store error — callers treat 'no session' as
    fail-closed (require the anchored test), unchanged.
    """
    try:
        from atdd.state.work_item_reader import WorkItemReader

        with WorkItemReader(control_root=repo_root) as reader:
            return reader.all_work_items()
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow)
        # An unreadable/uninitialisable store must not crash the validator; the
        # fail-closed caller then requires the test (status-quo behavior).
        return []


def owning_issue_phase(repo_root: Path, acc: RawAcceptance) -> Optional[str]:
    """Current lifecycle phase of the issue(s) owning *acc*, or ``None``.

    Maps *acc* to its wagon and reads every matching State Store work item's
    ``status`` (#1270 slice E — store-only, authoritative since #1203). Returns
    the MOST-ADVANCED phase among them (so a wagon counts as 'still pre-test'
    only when *every* owning work item is pre-test); returns ``None`` when no
    work item maps the wagon — the caller fails closed and requires the anchored
    test. Read-only.
    """
    wagon = _acceptance_wagon(acc)
    if not wagon:
        return None
    sessions = [
        s for s in _store_work_items(repo_root)
        if s.get("wagon") == wagon or s.get("train") == wagon
    ]
    if not sessions:
        return None
    order = _linear_phase_order()

    def _rank(status) -> int:
        return order.index(status) if status in order else len(order)

    best = max(sessions, key=lambda s: _rank(s.get("status")))
    status = best.get("status")
    return status if isinstance(status, str) and status else None


__all__ = [
    "RawAcceptance",
    "SUBSTRATE_BACKLOG_ENV",
    "acceptance_phase",
    "acceptance_urn",
    "assert_substrate_strict",
    "find_disposition_path",
    "has_harness_type",
    "has_signal_metric_and_threshold",
    "is_pre_test_phase",
    "iter_feature_files",
    "iter_repo_acceptances",
    "iter_repo_wmbts",
    "owning_issue_phase",
    "scan_test_acceptance_headers",
    "yaml_path_str",
]
