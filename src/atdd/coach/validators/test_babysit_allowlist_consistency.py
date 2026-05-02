# URN: component:govern-lifecycle:enforcement-substrate:test_babysit_allowlist_consistency:backend:domain
# Runtime: python
# Purpose: Validate the babysit Bash allow/deny pattern lists declared in orchestration.convention.yaml.

"""
Coach validator for babysit Bash allow/deny pattern lists (issue #366).

Loads ``babysit.bash_auto_approve_patterns`` and ``babysit.bash_deny_patterns``
from ``src/atdd/coach/conventions/orchestration.convention.yaml`` and enforces:

  1. Every rule's ``regex`` compiles cleanly.
  2. Every rule's ``id`` matches the rule-ID grammar
     (``<DOMAIN>-<TOPIC>-<NNN>``) per SPEC-COACH-RULEID-0001 and uses
     DOMAIN=COACH per SPEC-COACH-RULEID-0002.
  3. Every rule's ``severity`` is an integer in [1, 5]
     (SPEC-COACH-RULEID-0003).
  4. Every rule's ``description`` is a non-empty string
     (SPEC-COACH-RULEID-0006).
  5. No regex appears in *both* the allow and deny lists (a synthetic
     overlap-on-test-corpus check).

Failures are emitted as structured ``Violation`` records (issue #340 substrate)
so that downstream risk-routing and self-fix tooling can key off ``rule_id``.

Run:
    PYTHONPATH=src python3 -m pytest -q \\
        src/atdd/coach/validators/test_babysit_allowlist_consistency.py -v
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

import pytest
import yaml

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.validators._violation import Violation


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
ORCHESTRATION_CONVENTION = (
    ATDD_PKG_DIR / "coach" / "conventions" / "orchestration.convention.yaml"
)


_RULE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+){2,4}$")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def _load_convention() -> Dict:
    if not ORCHESTRATION_CONVENTION.is_file():
        # Fallback to repo checkout (editable install).
        repo_path = (
            find_repo_root()
            / "src"
            / "atdd"
            / "coach"
            / "conventions"
            / "orchestration.convention.yaml"
        )
        if not repo_path.is_file():
            pytest.fail(
                f"orchestration convention missing at {ORCHESTRATION_CONVENTION} "
                f"(also looked at {repo_path})"
            )
        path = repo_path
    else:
        path = ORCHESTRATION_CONVENTION
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def _extract_pattern_rules(data: Dict, key: str) -> List[Tuple[str, Dict]]:
    """Return [(yaml_path, rule_dict), ...] for ``babysit.<key>.rules``."""
    babysit = data.get("babysit") or {}
    block = babysit.get(key) or {}
    rules = block.get("rules") or []
    return [(f"babysit.{key}.rules[{i}]", r) for i, r in enumerate(rules)]


# ---------------------------------------------------------------------------
# Per-rule validators (each emits a Violation on failure)
# ---------------------------------------------------------------------------
def _validate_rule(loc: str, rule: Dict) -> List[Violation]:
    violations: List[Violation] = []
    rule_id = rule.get("id", "")
    sev = rule.get("severity")
    desc = rule.get("description")
    regex_str = rule.get("regex")

    # Grammar — rule_id present and matches grammar.
    if not isinstance(rule_id, str) or not _RULE_ID_PATTERN.match(rule_id):
        violations.append(
            Violation(
                rule_id="COACH-BABYSIT-001",
                severity=3,
                location=f"orchestration.convention.yaml:{loc}",
                detail=f"rule id {rule_id!r} does not match grammar <DOMAIN>-<TOPIC>-<NNN>",
            )
        )
    elif not rule_id.startswith("COACH-BABYSIT-"):
        violations.append(
            Violation(
                rule_id="COACH-BABYSIT-002",
                severity=3,
                location=f"orchestration.convention.yaml:{loc}",
                detail=(
                    f"rule id {rule_id!r} must use DOMAIN=COACH and "
                    f"TOPIC=BABYSIT for babysit pattern rules"
                ),
            )
        )

    # Severity in [1, 5].
    if isinstance(sev, bool) or not isinstance(sev, int) or not (1 <= sev <= 5):
        violations.append(
            Violation(
                rule_id="COACH-BABYSIT-003",
                severity=3,
                location=f"orchestration.convention.yaml:{loc}",
                detail=f"severity must be int in [1, 5], got {sev!r}",
            )
        )

    # Description non-empty.
    if not isinstance(desc, str) or not desc.strip():
        violations.append(
            Violation(
                rule_id="COACH-BABYSIT-004",
                severity=2,
                location=f"orchestration.convention.yaml:{loc}",
                detail="description must be a non-empty string",
            )
        )

    # Regex compiles.
    if not isinstance(regex_str, str) or not regex_str:
        violations.append(
            Violation(
                rule_id="COACH-BABYSIT-005",
                severity=4,
                location=f"orchestration.convention.yaml:{loc}",
                detail="regex must be a non-empty string",
            )
        )
    else:
        try:
            re.compile(regex_str)
        except re.error as exc:
            violations.append(
                Violation(
                    rule_id="COACH-BABYSIT-005",
                    severity=4,
                    location=f"orchestration.convention.yaml:{loc}",
                    detail=f"regex does not compile: {exc}",
                )
            )

    return violations


# ===========================================================================
# Tests
# ===========================================================================


def test_babysit_allow_patterns_well_formed():
    """Every allow-list entry has a valid id/severity/description/regex."""
    data = _load_convention()
    rules = _extract_pattern_rules(data, "bash_auto_approve_patterns")
    assert rules, (
        "babysit.bash_auto_approve_patterns.rules is empty — at minimum, the "
        "evidence-seeded patterns from issue #366 (read-only git, pytest, "
        "ls/cat/grep) must be declared"
    )

    violations: List[Violation] = []
    for loc, rule in rules:
        violations.extend(_validate_rule(loc, rule))

    if violations:
        pytest.fail(
            "\n\nbabysit allow-pattern rule violations:\n\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


def test_babysit_deny_patterns_well_formed():
    """Every deny-list entry has a valid id/severity/description/regex."""
    data = _load_convention()
    rules = _extract_pattern_rules(data, "bash_deny_patterns")
    assert rules, (
        "babysit.bash_deny_patterns.rules is empty — at minimum, network "
        "egress (curl/wget) and destructive ops (rm/mv) must be denied"
    )

    violations: List[Violation] = []
    for loc, rule in rules:
        violations.extend(_validate_rule(loc, rule))

    if violations:
        pytest.fail(
            "\n\nbabysit deny-pattern rule violations:\n\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


def test_babysit_allow_and_deny_patterns_disjoint_on_test_corpus():
    """No published command should match both allow and deny lists.

    The spec mandates deny-then-allow precedence in the runtime classifier,
    but a published *overlap* almost always indicates author error — either
    the allow is too broad or the deny is too narrow. We exercise this with
    a synthetic test corpus seeded from the issue's evidence.
    """
    data = _load_convention()
    allow = [
        (loc, rule, re.compile(rule["regex"]))
        for (loc, rule) in _extract_pattern_rules(data, "bash_auto_approve_patterns")
        if isinstance(rule.get("regex"), str)
    ]
    deny = [
        (loc, rule, re.compile(rule["regex"]))
        for (loc, rule) in _extract_pattern_rules(data, "bash_deny_patterns")
        if isinstance(rule.get("regex"), str)
    ]

    corpus = [
        # Allow-list evidence.
        "git status --short",
        "git log --oneline -5",
        "git diff HEAD~1",
        "pytest -xvs",
        "ls -la",
        "cat README.md",
        "grep -r foo .",
        "echo hello",
        "pwd",
        # Deny-list evidence.
        "curl https://example.com",
        "wget https://x.com/y",
        "rm -rf /tmp/foo",
        "mv old new",
        "git push origin main",
        "git reset --hard HEAD",
        "pip install requests",
    ]

    overlaps: List[Violation] = []
    for cmd in corpus:
        a_hits = [(rule, loc) for (loc, rule, rgx) in allow if rgx.match(cmd)]
        d_hits = [(rule, loc) for (loc, rule, rgx) in deny if rgx.match(cmd)]
        if a_hits and d_hits:
            a_id = a_hits[0][0].get("id", "<unknown>")
            d_id = d_hits[0][0].get("id", "<unknown>")
            overlaps.append(
                Violation(
                    rule_id="COACH-BABYSIT-006",
                    severity=3,
                    location=f"orchestration.convention.yaml:babysit",
                    detail=(
                        f"command {cmd!r} matches both allow {a_id} and "
                        f"deny {d_id} — narrow the allow regex"
                    ),
                )
            )

    if overlaps:
        pytest.fail(
            "\n\nbabysit allow/deny overlap on test corpus:\n\n"
            + "\n".join(f"  - {v}" for v in overlaps)
        )


def test_babysit_pattern_ids_unique():
    """Allow + deny IDs together must be globally unique."""
    data = _load_convention()
    rules = _extract_pattern_rules(data, "bash_auto_approve_patterns") + \
            _extract_pattern_rules(data, "bash_deny_patterns")
    seen: Dict[str, List[str]] = {}
    for loc, rule in rules:
        rid = rule.get("id")
        if isinstance(rid, str) and rid:
            seen.setdefault(rid, []).append(loc)
    duplicates = {rid: locs for rid, locs in seen.items() if len(locs) > 1}
    if duplicates:
        msg = "\n".join(
            f"  {rid}: {locs}" for rid, locs in sorted(duplicates.items())
        )
        pytest.fail(f"\n\nDuplicate babysit rule IDs:\n\n{msg}")
