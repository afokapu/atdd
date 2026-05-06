# URN: component:govern-lifecycle:enforcement-substrate:test_acceptance_disposition:backend:tests
# Runtime: python
# Purpose: Substrate enforcement (#410) — repo YAML must NOT declare disposition: anywhere (the substrate sets it to strict).

"""Substrate Class 1 conformance: forbid disposition: in repo YAML (spec v12 §7.3).

Repo contract rules are unsuppressible by construction (§2). The walker
sets ``disposition = "strict"`` unconditionally per §4.4. Allowing a
``disposition:`` field in repo YAML is misleading because the value is
ignored.

This validator scans, for every repo file:

  - WMBT YAMLs       (``plan/<wagon>/[DLPCEMYRK]NNN.yaml``)
  - train YAMLs      (``plan/_trains/*.yaml``)
  - feature YAMLs    (``plan/<wagon>/feature.yaml::security.abuse_cases[]``)

Any nested ``disposition:`` field — at any depth, in any structure —
fires the rule. The security path is a no-op pre-#419 (no abuse_cases
exist in the wild yet); post-#419 it covers them without code change.

Failures route through ``assert_disposition_satisfied`` under
``tester.acceptance-violation.disposition-must-not-be-declared`` (strict).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.tester.validators._acceptance_walker import (
    assert_substrate_strict,
    find_disposition_path,
    iter_feature_files,
    yaml_path_str,
)


pytestmark = [pytest.mark.platform]


_RULE = bind_rule("tester.acceptance-violation.disposition-must-not-be-declared")
_VALIDATOR_ID = (
    "test_acceptance_disposition::test_no_disposition_in_repo_yaml"
)


def _scan_yaml_for_disposition(
    path: Path,
    *,
    subtree_keys: Optional[tuple] = None,
) -> Optional[tuple]:
    """Return the YAML key path to the first ``disposition:`` in *path*, or None.

    When *subtree_keys* is given, scope the search to that nested key path
    (used to scope feature.yaml scanning to ``security.abuse_cases``).
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict):
        return None

    node = data
    parts: tuple = ()
    if subtree_keys:
        for key in subtree_keys:
            if not isinstance(node, dict) or key not in node:
                return None
            node = node[key]
            parts = parts + (key,)

    sub = find_disposition_path(node, parts)
    return sub


def collect_violations(repo_root: Optional[Path] = None) -> List[Violation]:
    """Walk plan/ and return disposition-declaration violations."""
    root = Path(repo_root).resolve() if repo_root is not None else find_repo_root()
    violations: List[Violation] = []

    plan_dir = root / "plan"
    if not plan_dir.is_dir():
        return violations

    # WMBT files: plan/<wagon>/[DLPCEMYRK]NNN.yaml
    import re

    wmbt_re = re.compile(r"^[DLPCEMYRK]\d{3}\.yaml$")
    for wagon_dir in sorted(plan_dir.iterdir()):
        if not wagon_dir.is_dir() or wagon_dir.name.startswith("_"):
            continue
        for wmbt_file in sorted(wagon_dir.glob("*.yaml")):
            if not wmbt_re.match(wmbt_file.name):
                continue
            bad = _scan_yaml_for_disposition(wmbt_file)
            if bad is not None:
                violations.append(_make_violation(wmbt_file, bad, root))

    # Train files: plan/_trains/*.yaml
    trains_dir = plan_dir / "_trains"
    if trains_dir.is_dir():
        for train_file in sorted(trains_dir.glob("*.yaml")):
            bad = _scan_yaml_for_disposition(train_file)
            if bad is not None:
                violations.append(_make_violation(train_file, bad, root))

    # Feature files: plan/<wagon>/feature.yaml — scope to security.abuse_cases
    # so an unrelated disposition: outside the security block doesn't fire
    # (feature.yaml has many subtrees the substrate rule doesn't govern).
    for feature_file in iter_feature_files(root):
        bad = _scan_yaml_for_disposition(
            feature_file,
            subtree_keys=("security", "abuse_cases"),
        )
        if bad is not None:
            violations.append(_make_violation(feature_file, bad, root))

    return violations


def _make_violation(path: Path, parts: tuple, repo_root: Path) -> Violation:
    try:
        rel = str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        rel = str(path)
    detail = (
        f"YAML at {rel!r} declares 'disposition:' at path "
        f"{yaml_path_str(parts)!r} — repo contract rules are unsuppressible by "
        f"construction (§2); the walker sets disposition='strict' "
        f"unconditionally (§4.4)."
    )
    return Violation(
        rule_id=_RULE.rule_id,
        severity=_RULE.severity,
        location=f"{rel}:{yaml_path_str(parts)}",
        detail=detail,
        fix_hint_ref=_RULE.fix_hint_ref,
    )


def test_no_disposition_in_repo_yaml() -> None:
    """Repo YAML must NOT declare 'disposition:' anywhere (§7.3)."""
    violations = collect_violations()
    assert_substrate_strict(_VALIDATOR_ID, violations)


__all__ = ["collect_violations", "test_no_disposition_in_repo_yaml"]
