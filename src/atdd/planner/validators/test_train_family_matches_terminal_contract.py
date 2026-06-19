"""Validator: planner.train.family-matches-terminal-contract (#1085 / #1083).

A train's declared ``family`` MUST agree with its declared terminal contract:

- ``family: delivery``  <=>  the terminal step's primary artifact is
  ``platform:acceptance:commit-receipt`` (a durable Acceptance Authority commit).
- ``family: behavior``  otherwise.
- ``family`` is OPTIONAL during the #1083 transition; a train without it is not
  flagged. Presence becomes required later.

PENDING BINDING (#1054): the rule is declared as a convention node
``planner.train.family-matches-terminal-contract`` (status: draft) but is not yet
wired through ``bind_rule()`` / the disposition gate, because the legacy registry
binder reads a ``rules:`` block and ``train.convention.yaml`` has none yet — that
block is owned by #1054 (Bind Unbound Substrate Validators). When #1054 lands the
train ``rules:`` block, add::

    from atdd.coach.utils.rule_binding import bind_rule
    from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
    _RULE = bind_rule("planner.train.family-matches-terminal-contract")

and route the integration violations through ``assert_disposition_satisfied``.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from atdd.coach.utils.repo import find_repo_root

try:  # pragma: no cover - yaml is always present in the toolkit
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

COMMIT_RECEIPT = "platform:acceptance:commit-receipt"
VALID_FAMILIES = ("behavior", "delivery")


def check_family_matches_terminal(train: dict) -> Optional[str]:
    """Return a violation string if ``family`` disagrees with the terminal
    contract, else ``None``. A train with no ``family`` is not flagged (the field
    is optional during the #1083 transition)."""
    family = train.get("family")
    if family is None:
        return None
    tid = train.get("train_id", "<unknown>")
    if family not in VALID_FAMILIES:
        return f"{tid}: family must be one of {VALID_FAMILIES}, got {family!r}"
    sequence = train.get("sequence") or []
    terminal_artifact = sequence[-1].get("artifact") if sequence else None
    terminal_is_receipt = terminal_artifact == COMMIT_RECEIPT
    if terminal_is_receipt and family != "delivery":
        return (
            f"{tid}: terminal artifact is {COMMIT_RECEIPT} but family={family!r} "
            f"- an Acceptance Authority commit means family must be 'delivery'"
        )
    if family == "delivery" and not terminal_is_receipt:
        return (
            f"{tid}: family='delivery' but terminal artifact is {terminal_artifact!r} "
            f"- a delivery train must terminate in {COMMIT_RECEIPT}"
        )
    return None


def _load_trains(repo_root: Path) -> List[dict]:
    trains_dir = repo_root / "plan" / "_trains"
    trains: List[dict] = []
    if yaml is None or not trains_dir.is_dir():
        return trains
    for f in sorted(trains_dir.glob("*.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("train_id"):
            trains.append(data)
    return trains


# --- unit tests: prove the check logic against fixtures ---

def test_check_flags_behavior_with_commit_receipt_terminal():
    train = {"train_id": "9001-x", "family": "behavior",
             "sequence": [{"step": 1, "artifact": COMMIT_RECEIPT}]}
    assert check_family_matches_terminal(train) is not None


def test_check_flags_delivery_without_commit_receipt_terminal():
    train = {"train_id": "9002-x", "family": "delivery",
             "sequence": [{"step": 1, "artifact": "identity:sign-in:session-created"}]}
    assert check_family_matches_terminal(train) is not None


def test_check_passes_delivery_with_commit_receipt():
    train = {"train_id": "9003-x", "family": "delivery",
             "sequence": [{"step": 1, "artifact": COMMIT_RECEIPT}]}
    assert check_family_matches_terminal(train) is None


def test_check_passes_behavior_without_commit_receipt():
    train = {"train_id": "9004-x", "family": "behavior",
             "sequence": [{"step": 1, "artifact": "identity:sign-in:session-created"}]}
    assert check_family_matches_terminal(train) is None


def test_check_skips_train_without_family():
    train = {"train_id": "9005-x",
             "sequence": [{"step": 1, "artifact": COMMIT_RECEIPT}]}
    assert check_family_matches_terminal(train) is None


def test_check_flags_invalid_family():
    train = {"train_id": "9006-x", "family": "bogus", "sequence": []}
    assert check_family_matches_terminal(train) is not None


# --- integration: no real train violates (vacuous until trains adopt `family`) ---

def test_real_trains_family_matches_terminal_contract():
    repo_root = find_repo_root()
    violations = [
        v
        for t in _load_trains(repo_root)
        if (v := check_family_matches_terminal(t)) is not None
    ]
    assert not violations, (
        "family<->terminal-contract violations:\n  " + "\n  ".join(violations)
    )
