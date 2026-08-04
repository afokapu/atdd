# Component: component:govern-lifecycle:bind-issue-train:TrainBindingScanner:backend:domain
"""Scan issue train references against the repository's train registry (#1590).

Holds an atdd-issue's declared train to two things, kept as two SEPARATE rules
because their dispositions and their measured populations differ by two orders of
magnitude:

* ``coach.train-reference.resolves-to-registered-train`` — the reference must
  RESOLVE. A placeholder (``TBD``, ``N/A``) is malformed; a well-formed identity
  no registry declares is unregistered. Measured 2026-08-03: 16 of 175.
* ``coach.train-reference.resolved-train-has-interlocking`` — the train it
  resolved to should be routed through by some interlocking. Measured
  2026-08-03: 148 of 159.

Pure scan: takes issue records in, returns violations out. No store access and no
provider call, so the shipped validator, a CI job and a unit test all drive the
same function over whatever records they have.

BOUNDARY: the resolution primitive lives planner-side
(``atdd.planner.commands.train_binding``) because the write-side guards in
``author_publish`` need it too and the planner tree may not import ``atdd.coach``.
This module DELEGATES there — coach → planner, never the reverse.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.planner.commands.train_binding import (
    interlocking_index, plan_is_available, resolve_train,
)

_RULE = bind_rule("coach.train-reference.resolves-to-registered-train")
_INTERLOCKING_RULE = bind_rule("coach.train-reference.resolved-train-has-interlocking")

#: Terminal issues are historical; a broken reference there is not actionable.
_TERMINAL = {"COMPLETE", "OBSOLETE"}


def _violation(rule, number: Any, detail: str) -> Violation:
    return Violation(
        rule_id=rule.rule_id,
        severity=rule.severity,
        location=f"github-issue#{number}:train",
        detail=detail,
        fix_hint_ref=getattr(rule, "fix_hint_ref", None),
    )


def scan_train_references(
    issues: Iterable[Dict[str, Any]],
    *,
    plan_root: Optional[Path] = None,
) -> List[Violation]:
    """Violations for every issue whose train reference is broken or unrouted.

    Each record needs ``number``; ``train`` is the stored reference and ``status``
    the lifecycle state. ``plan_root`` is the checkout whose registry the
    references resolve against (the repo root, NOT the ``plan/`` directory) — the
    repository under scan, never the toolkit's own.

    A repo with no ``plan/`` tree has no registry, so there is nothing to hold the
    references to and nothing is reported.
    """
    violations: List[Violation] = []
    if not plan_is_available(plan_root):
        return violations

    # Built once and threaded through: a 175-issue scan must not re-read every
    # interlocking artifact 175 times.
    index = interlocking_index(plan_root)
    routed_at_all = bool(index)

    for issue in issues:
        number = issue.get("number")
        if str(issue.get("status") or "").upper() in _TERMINAL:
            continue

        declared = (issue.get("train") or "").strip() or None
        if declared is None:
            # A train is optional for the issue types that do not require one.
            # This rule governs a reference that WAS set (see the node's
            # exceptions); the train-required gate is a separate concern.
            continue

        verdict = resolve_train(declared, plan_root, interlockings=index)
        if not verdict.resolved:
            violations.append(_violation(_RULE, number, verdict.detail))
            # An unresolvable reference has no resolved train whose interlocking
            # could be missing. Reporting both would double-count one defect.
            continue

        if routed_at_all and not verdict.has_interlocking:
            violations.append(_violation(
                _INTERLOCKING_RULE,
                number,
                f"train {verdict.train_id} is registered but no interlocking in "
                f"this repository routes through it, so a gate reading this "
                f"train's interlocking has no subject to read",
            ))

    return violations


def scan_store_train_references(control_root: Optional[Path] = None) -> List[Violation]:
    """Scan every issue-backed work item in the local State Store.

    Store-only by design: no GitHub call, so the shipped validator carries
    neither the ``github_api`` nor the ``platform`` marker and is therefore
    selected by ``atdd validate coach --local --skip-api`` rather than silently
    deselected by its marker expression.
    """
    from atdd.coach.commands.issue_feature_binding import (
        GITHUB_PROVIDER, ISSUE_REF_KIND, _open_store,
    )

    store = _open_store(control_root)
    rows = store.conn.execute(
        "SELECT r.ref_value, o.state, o.data FROM external_refs r "
        "JOIN objects o ON o.uid = r.object_uid "
        "WHERE r.provider = ? AND r.ref_kind = ?",
        (GITHUB_PROVIDER, ISSUE_REF_KIND),
    ).fetchall()

    import json

    issues: List[Dict[str, Any]] = []
    for ref_value, state, data in rows:
        payload = json.loads(data) if data else {}
        issues.append({
            "number": ref_value,
            "status": state,
            "train": payload.get("train"),
        })
    return scan_train_references(issues, plan_root=control_root)
