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
from typing import Iterator, Optional, Sequence

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
      - ``plan/<wagon>/[DLPCEMYRK]NNN.yaml`` (WMBT acceptances).
      - ``plan/_trains/*.yaml``               (train acceptances).

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
        for train_file in sorted(trains_dir.glob("*.yaml")):
            yield from _iter_acceptances_in_file(train_file, "train", repo_root)


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


__all__ = [
    "RawAcceptance",
    "SUBSTRATE_BACKLOG_ENV",
    "acceptance_phase",
    "acceptance_urn",
    "assert_substrate_strict",
    "find_disposition_path",
    "has_harness_type",
    "has_signal_metric_and_threshold",
    "iter_feature_files",
    "iter_repo_acceptances",
    "yaml_path_str",
]
