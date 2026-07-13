# URN: component:enforce-merge-authority:test-support:merge_authority_helpers:backend:tests
# Runtime: python
# Purpose: Hermetic git-checkout, canonical-projection and commit-trailer fixtures shared by the enforce-merge-authority acceptances.

"""Shared, hermetic fixtures for the enforce-merge-authority acceptances (#1400).

The merge authority is defined *against git*: the legal-transition gate diffs the head
projection against the merge-base, and the cross-check reads the commit message that
carried the diff. So these fixtures build a real repository with real commits carrying
real ATDD trailers, under ``tmp_path``.

It is still hermetic — a throwaway repo, a throwaway Control Root, **no provider and no
network anywhere** — which is the property the wagon exists to prove: the whole gate is
satisfiable by ``git`` alone (I7, spec §4).

Projections are written through :func:`atdd.state.projection.canonical_bytes`, never by a
hand-rolled dump, so a fixture branch is *canonical by construction*. That matters: the
acceptances are about a projection that passes canonicality and schema and is illegal
anyway, and a fixture that failed canonicality would prove nothing.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from atdd.state.projection import PROJECTION_RELATIVE, canonical_bytes, object_digest

#: Pinned identities, so a fixture's bytes never move between runs.
UID_X = "wi_01HF7YAT00M78607F0000000X1"
UID_Y = "wi_01HF7YAT00M78607F0000000Y2"

#: A pinned, obviously-fake digest for a trailer that only has to be *well-formed*.
TOKEN_DIGEST = "sha256:" + "a1" * 32


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return its stdout."""
    result = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=True, timeout=60,
    )
    return result.stdout.strip()


def checkout(path: Path) -> Path:
    """A real git repo with a Control Root, a gitignored store, and one commit."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--quiet", "--initial-branch=main", str(path)],
        check=True, capture_output=True, timeout=60,
    )
    git(path, "config", "user.email", "dev@example.invalid")
    git(path, "config", "user.name", "Dev")
    (path / ".atdd").mkdir(exist_ok=True)
    (path / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    (path / ".gitignore").write_text(
        ".atdd/state/state.sqlite*\n.atdd/version_cache.json\n", encoding="utf-8",
    )
    (path / ".atdd" / "state" / "projection").mkdir(parents=True, exist_ok=True)
    (path / ".atdd" / "state" / "projection" / ".gitkeep").write_text("", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "--quiet", "-m", "initial")
    return path


def document(
    uid: str,
    *,
    phase: str = "PLANNED",
    state: str = "ACTIVE",
    owner: str = "dev-a",
    **extra: Any,
) -> Dict[str, Any]:
    """A valid ``commons:projection-object`` document."""
    doc: Dict[str, Any] = {
        "uid": uid,
        "phase": phase,
        "state": state,
        "owner_actor": owner,
        "slug": uid.lower(),
    }
    doc.update(extra)
    return doc


def projection_dir(repo: Path) -> Path:
    return repo / PROJECTION_RELATIVE


def write_projection(repo: Path, documents: Iterable[Mapping[str, Any]]) -> Path:
    """Write ``documents`` as the repo's committed projection, in CANONICAL bytes.

    Canonical by construction: the fixtures exist to show that canonicality is *not*
    correctness, so a branch that failed canonicality would be arguing the wrong point.
    """
    out = projection_dir(repo)
    out.mkdir(parents=True, exist_ok=True)
    for doc in documents:
        (out / f"{doc['uid']}.yaml").write_bytes(canonical_bytes(doc))
    return out


def digest_of(doc: Mapping[str, Any]) -> str:
    """The ``ATDD-Projection-Digest`` a commit carrying ``doc`` must declare."""
    return object_digest(doc)


def trailer_block(
    uid: str,
    *,
    transition: Optional[str] = None,
    token_digest: Optional[str] = None,
    gate: Optional[str] = None,
    projection_digest: Optional[str] = None,
) -> str:
    """One object's ATDD trailer group, as it appears at the foot of a commit message."""
    lines = [f"ATDD-Object: {uid}"]
    if transition is not None:
        lines.append(f"ATDD-Transition: {transition}")
    if token_digest is not None:
        lines.append(f"ATDD-Token-Digest: {token_digest}")
    if gate is not None:
        lines.append(f"ATDD-Gate: {gate}")
    if projection_digest is not None:
        lines.append(f"ATDD-Projection-Digest: {projection_digest}")
    return "\n".join(lines)


def message(subject: str, *blocks: str) -> str:
    """A commit message: a subject, a blank line, then the trailer group(s)."""
    return subject + "\n\n" + "\n\n".join(block for block in blocks if block) + "\n"


def commit_all(repo: Path, msg: str) -> str:
    """Stage everything and commit with ``msg``; return the new HEAD sha."""
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "--allow-empty", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD")


def touch_test_file(repo: Path, name: str = "test_acceptance.py") -> Path:
    """A changed test file — the commit's *test evidence* (spec §6, the v1 derivation)."""
    path = repo / "tests" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("def test_placeholder() -> None:\n    assert True\n", encoding="utf-8")
    return path


def touch_source_file(repo: Path, name: str = "thing.py") -> Path:
    """A changed source file — the commit's *implementation diff*."""
    path = repo / "src" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("VALUE = 1\n", encoding="utf-8")
    return path


def repo_root() -> Path:
    """This working copy's repository root — where the policy and the workflow live."""
    return Path(__file__).resolve().parents[5]


def contract(name: str) -> Dict[str, Any]:
    """An authored contract from ``contracts/commons/`` — the schema source of truth."""
    import json

    path = repo_root() / "contracts" / "commons" / f"{name}.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def evidence_tokens(*tokens: str) -> List[str]:
    """A readable spelling of an evidence set in the acceptance matrices."""
    return list(tokens)
