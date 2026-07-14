# URN: component:govern-projection-fields:test-support:ownership_helpers:backend:tests
# Runtime: python
# Purpose: Hermetic projection-document, field-ownership-policy and three-way-merge fixtures shared by the govern-projection-fields acceptances.

"""Shared, hermetic fixtures for the govern-projection-fields acceptances (#1400).

Ownership and merge safety are claims about *documents* — a base, an ours and a theirs —
so these fixtures build them directly rather than through a store. What they do not do is
hand-roll the bytes: a projection written here goes through
:func:`atdd.state.projection.canonical_bytes`, so a fixture branch is canonical by
construction. That matters, because the wagon's whole argument is that canonicality is not
correctness — and a fixture that failed canonicality would be arguing the wrong point.

The policy fixtures are *derived* from the shipped table rather than retyped, so a variant
differs from the real policy in exactly the one way its acceptance is about (an omitted
field, an unknown writer) and in no other way nobody meant.
"""
from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import yaml

from atdd.state.ownership import DEFAULT_POLICY, POLICY_RELATIVE
from atdd.state.projection import canonical_bytes

from .._fixtures import STORE_ONLY_GITIGNORE
from .._fixtures import checkout as _checkout
from .._fixtures import (  # re-exported: the acceptances import these from this module
    commit_all,
    git,
    write_projection,
)

#: Pinned identities, so a fixture's bytes never move between runs.
UID_X = "wi_01HF7YAT00M78607F0000000X1"
UID_Y = "wi_01HF7YAT00M78607F0000000Y2"

#: The evidence a PLANNED -> GREEN jump must carry: both gates it passes through (§6).
PLANNED_TO_GREEN = (
    "operator_token_digest", "gate_id", "failing_test_evidence",
    "passing_test_evidence", "implementation_diff",
)

#: The evidence PLANNED -> RED alone demands.
PLANNED_TO_RED = ("operator_token_digest", "gate_id", "failing_test_evidence")


def document(uid: str = UID_X, **overrides: Any) -> Dict[str, Any]:
    """A valid ``commons:projection-object``."""
    doc: Dict[str, Any] = {
        "uid": uid,
        "slug": "feature-x",
        "phase": "PLANNED",
        "state": "ACTIVE",
        "owner_actor": "dev-a",
    }
    doc.update(overrides)
    return doc


def projection(*documents: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """A projection keyed by uid — the shape every validator takes."""
    return {str(doc["uid"]): dict(doc) for doc in documents}


def write_document(path: Path, doc: Mapping[str, Any]) -> Path:
    """One projection object at an explicit path, in canonical bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(doc))
    return path


def policy_document(
    *, omit: Optional[str] = None, writer: Optional[Dict[str, str]] = None,
    rule: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """The shipped policy, varied in exactly one way.

    ``omit`` drops a field's entry (a coverage gap); ``writer``/``rule`` rewrite one field's
    declaration. Everything else stays byte-identical to what ships, so an acceptance that
    fails is failing about the variation and nothing else.
    """
    document = copy.deepcopy(DEFAULT_POLICY)
    entries: List[Dict[str, Any]] = []
    for entry in document["fields"]:
        name = entry["field"]
        if name == omit:
            continue
        if writer and name in writer:
            entry["writer"] = writer[name]
        if rule and name in rule:
            entry["rule"] = rule[name]
        entries.append(entry)
    return {"fields": entries}


def write_policy(root: Path, document: Mapping[str, Any]) -> Path:
    """Commit a policy document at the path the loader looks for."""
    path = Path(root) / POLICY_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(dict(document), sort_keys=False), encoding="utf-8")
    return path


def repo_root() -> Path:
    """This working copy's repository root — where the real policy and contracts live."""
    return Path(__file__).resolve().parents[5]


def shipped_policy_document() -> Dict[str, Any]:
    """The policy this repository actually commits — not a fixture's idea of it."""
    return yaml.safe_load((repo_root() / POLICY_RELATIVE).read_text(encoding="utf-8"))


def contract(name: str) -> Dict[str, Any]:
    """An authored contract from ``contracts/commons/`` — the schema source of truth."""
    return json.loads(
        (repo_root() / "contracts" / "commons" / f"{name}.schema.json").read_text(encoding="utf-8")
    )


def checkout(path: Path) -> Path:
    """A real git repo with a Control Root and one commit."""
    return _checkout(path, gitignore=STORE_ONLY_GITIGNORE)
