# URN: component:govern-lifecycle:enforcement-substrate:rule_disposition_required:backend:domain
# Runtime: python
# Purpose: Every declared rule must carry a disposition (strict | suppress-and-clean | advisory).

"""
Coach validator for rule disposition coverage (issue #395).

Walks every ``*.convention.yaml`` in the toolkit's ``conventions:`` migration
allowlist and asserts that each rule entry under ``rules:`` declares a
``disposition:`` field with one of the three legal values:

* ``strict`` — any violation fails CI
* ``suppress-and-clean`` — pre-existing violations carry inline
  ``# atdd:suppress(<rule_id>) [UNTIL=<YYYY-MM-DD>]`` markers; new ones fail
* ``advisory`` — emits warnings, never fails CI

Scope:
    Only conventions listed under ``rule-id.convention.yaml::migration.completed``
    are checked. Conventions outside that allowlist are skipped (they have
    no rule_id grammar opt-in yet, so adding ``disposition:`` is premature).

Failure mode:
    ``pytest.fail`` with a per-rule punch list of missing or invalid
    ``disposition`` declarations.

Rule emitted: ``coach.rule-id.disposition-required`` (severity 2, strict).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import pytest
import yaml

from atdd.coach.utils.rule_id_registry import build_registry
from atdd.coach.validators.test_rule_id_uniqueness import find_convention_files


pytestmark = [pytest.mark.coach, pytest.mark.platform]


_LEGAL_DISPOSITIONS = frozenset({"strict", "suppress-and-clean", "advisory"})


def _load_completed_allowlist() -> List[str]:
    """Return convention paths opted into strict rule-id grammar."""
    convention_files = find_convention_files()
    rule_id_path = next(
        (p for p in convention_files if p.name == "rule-id.convention.yaml"),
        None,
    )
    if rule_id_path is None:
        return []
    with open(rule_id_path) as fh:
        data = yaml.safe_load(fh) or {}
    completed = (data.get("migration") or {}).get("completed") or []
    return [str(p) for p in completed]


def _missing_dispositions() -> List[Tuple[str, Path, str]]:
    """Return ``[(rule_id, convention_path, reason), ...]`` for offenders.

    Reason is one of:
      - ``"missing"`` — no ``disposition:`` field declared
      - ``"invalid:<value>"`` — declared but not in the legal enum
    """
    allowlist = _load_completed_allowlist()
    if not allowlist:
        return []

    registry = build_registry()
    offenders: List[Tuple[str, Path, str]] = []

    # Index registry entries by their convention path's tail so we can match
    # the allowlist (which stores repo-relative paths) against absolute paths
    # in the registry.
    for rule_id, meta in registry.items():
        path_str = str(meta.convention_path)
        if not any(path_str.endswith(allowed) for allowed in allowlist):
            continue
        if meta.disposition is None:
            offenders.append((rule_id, meta.convention_path, "missing"))
        elif meta.disposition not in _LEGAL_DISPOSITIONS:
            offenders.append(
                (rule_id, meta.convention_path, f"invalid:{meta.disposition}")
            )

    offenders.sort(key=lambda r: (str(r[1]), r[0]))
    return offenders


def _format_offenders(offenders: List[Tuple[str, Path, str]]) -> str:
    by_path: Dict[Path, List[Tuple[str, str]]] = {}
    for rid, path, reason in offenders:
        by_path.setdefault(path, []).append((rid, reason))

    lines = [
        f"[ERROR] coach.rule-id.disposition-required: "
        f"{len(offenders)} rule(s) without a valid disposition:"
    ]
    for path in sorted(by_path):
        lines.append(f"  {path}")
        for rid, reason in sorted(by_path[path]):
            if reason == "missing":
                lines.append(f"    {rid}   missing disposition:")
            else:
                lines.append(f"    {rid}   {reason}")
    lines.append("")
    lines.append("  Add one of:")
    lines.append("    disposition: strict")
    lines.append("    disposition: suppress-and-clean")
    lines.append("    disposition: advisory")
    return "\n".join(lines)


@pytest.mark.coach
def test_rule_disposition_required():
    """Every migrated rule declares a legal ``disposition:`` field.

    Issue #395 replaces ``RatchetBaseline`` with disposition-driven gating.
    A rule without a disposition has no defined CI policy, so this test
    fails until every rule (in the migrated subset) declares one.
    """
    offenders = _missing_dispositions()
    if not offenders:
        return
    pytest.fail(_format_offenders(offenders))
