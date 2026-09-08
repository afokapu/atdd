# Component: component:govern-lifecycle:bind-issue-feature:FeatureBindingScanner:backend:domain
"""Scan issue feature bindings against the plan graph (#1635).

Holds an atdd-issue's declared feature to two things at once:

* it must RESOLVE — name a real feature YAML under ``plan/`` whose own ``urn:``
  matches. A train identity in the Feature slot does not (that is the #1626
  drift); nor does a well-formed URN for a feature nobody authored.
* the two records must AGREE — the body's ``Feature`` row and the stored
  ``work_item.data.feature``. Divergence was previously invisible: #1626 had a
  populated body and a NULL store, and #1635 itself carried a body naming one
  feature while its store named an unrelated one.

Pure scan: takes issue records in, returns violations out. No store access and
no provider call, so the shipped validator, a CI job and a unit test all drive
the same function over whatever records they have.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.planner.commands.feature_binding import feature_in_body, resolve_feature

_RULE = bind_rule("coach.issue.feature-binding-must-resolve")

#: Terminal issues are historical; a broken binding there is not actionable.
_TERMINAL = {"COMPLETE", "OBSOLETE"}


def _violation(number: Any, detail: str) -> Violation:
    return Violation(
        rule_id=_RULE.rule_id,
        severity=_RULE.severity,
        location=f"github-issue#{number}:feature",
        detail=detail,
        fix_hint_ref=getattr(_RULE, "fix_hint_ref", None),
    )


def scan_feature_bindings(
    issues: Iterable[Dict[str, Any]],
    *,
    plan_root: Optional[Path] = None,
) -> List[Violation]:
    """Violations for every issue whose feature binding is broken or divergent.

    Each record needs ``number``; ``feature`` is the stored binding and ``body``
    the issue body. ``plan_root`` is the checkout whose ``plan/`` tree the URNs
    resolve against (the repo root, not the ``plan/`` directory itself).
    """
    violations: List[Violation] = []

    for issue in issues:
        number = issue.get("number")
        if str(issue.get("status") or "").upper() in _TERMINAL:
            continue

        stored = (issue.get("feature") or None)
        declared = feature_in_body(issue.get("body"))

        # 1) Resolution. The stored binding is authoritative; fall back to the
        #    body's declaration so an unbound-but-declaring issue is reported
        #    against something concrete rather than merely as "no binding".
        subject = stored or declared
        verdict = resolve_feature(subject, plan_root)
        if not verdict.resolved:
            violations.append(_violation(number, verdict.detail))
            # An unresolvable binding makes the agreement check noise — the
            # value to fix is the one just reported.
            continue

        # 2) Agreement between the two records.
        if stored and declared and stored != declared:
            violations.append(_violation(
                number,
                f"the issue body declares feature {declared} but the store holds "
                f"{stored} — the two records disagree and a reader cannot tell "
                f"which is authoritative",
            ))
        elif stored and not declared:
            violations.append(_violation(
                number,
                f"the store holds feature {stored} but the issue body declares no "
                f"Feature row, so the binding is invisible to a human reader",
            ))
        elif declared and not stored:
            violations.append(_violation(
                number,
                f"the issue body declares feature {declared} but the stored "
                f"work_item.data.feature is NULL — the body updated and the store "
                f"did not (the #1626 shape)",
            ))

    return violations


def scan_store_bindings(control_root: Optional[Path] = None) -> List[Violation]:
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
            "feature": payload.get("feature"),
            "body": payload.get("body"),
        })
    return scan_feature_bindings(issues, plan_root=control_root)
