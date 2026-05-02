"""Fixture: COACH-PKG-LAYOUT-001 violations — find_repo_root + src/atdd path arithmetic."""

from pathlib import Path
from atdd.coach.utils.repo import find_repo_root


def direct_chain():
    return find_repo_root() / "src" / "atdd" / "coach" / "schemas" / "config.schema.json"


def single_literal():
    return find_repo_root() / "src/atdd/coach/conventions/foo.yaml"


def via_or_short_circuit(repo_root=None):
    return (repo_root or find_repo_root()) / "src" / "atdd" / "coach" / "commands"


def assigned_then_used():
    REPO_ROOT = find_repo_root()
    return REPO_ROOT / "src" / "atdd" / "tester" / "validators"


def nested_path_call():
    return Path(find_repo_root()) / "src" / "atdd" / "planner" / "schemas"
