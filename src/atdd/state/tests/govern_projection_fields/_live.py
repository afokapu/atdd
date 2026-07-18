# URN: component:govern-projection-fields:test-support:live_cli:backend:tests
# Runtime: python
# Purpose: Drive the real in-tree `atdd state` governance CLI — and a real `git merge` through the registered projection merge driver — against real checkouts of a real bare (non-GitHub) remote.

"""Live-CLI harness for the govern-projection-fields SMOKE acceptances (#1400).

Two things are driven for real here, and the second is the one that matters.

The first is the command surface: ``python -m atdd state ...`` by subprocess, against a real
checkout of a real **bare** remote — git object storage, no GitHub, no API, no provider.

The second is ``git merge`` **itself**. The merge driver is registered the way an operator
registers one (``merge.atdd-projection.driver`` + a ``.gitattributes`` entry) and then git
invokes it, on git's terms, with git's temp files. That is a materially stronger claim than
calling the driver's function with three paths: git decides when a driver runs at all, hands
it names that are not the uid, and interprets its exit code — and a driver that passes a
unit test but never gets invoked, or whose non-zero exit git ignores, has protected nothing.

``CI=true`` and a ``HOME`` pinned inside ``tmp_path`` keep every run hermetic.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence, Tuple

import yaml

from atdd.state.bare_remote import identify, seed_bare_remote

from .._fixtures import commit_all
from atdd.state.merge_driver import EVIDENCE_RELATIVE
from atdd.state.ownership import POLICY_RELATIVE

#: The in-tree ``src/`` root, so every subprocess drives THIS working copy's CLI.
_SRC = Path(__file__).resolve().parents[4]

#: The repository root — the real committed policy lives there.
_REPO = Path(__file__).resolve().parents[5]

#: The merge-driver name a checkout registers the driver under.
DRIVER = "atdd-projection"


def _env(root: Path) -> dict:
    return {
        "PYTHONPATH": str(_SRC),
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(root),
        "CI": "true",
    }


def atdd_state(root: Path, *args: str) -> subprocess.CompletedProcess:
    """Run ``atdd state <args> --root <root>`` and capture its result."""
    return subprocess.run(
        [sys.executable, "-m", "atdd", "state", *args, "--root", str(root)],
        cwd=str(root), env=_env(root), capture_output=True, text=True, timeout=180,
    )


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run git in ``repo`` with the CLI's environment, so an invoked driver can import atdd."""
    result = subprocess.run(
        ["git", *args], cwd=str(repo), env={**os.environ, **_env(repo)},
        capture_output=True, text=True, timeout=180,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stdout}{result.stderr}")
    return result


def out(repo: Path, *args: str) -> str:
    return git(repo, *args).stdout.strip()


def _seed_policy_and_driver(seed: Path) -> None:
    install_policy(seed)
    register_merge_driver(seed)


def bare_remote(tmp_path: Path) -> Path:
    """A bare git remote carrying ``main``: git object storage and nothing else."""
    return seed_bare_remote(
        tmp_path,
        message="seed: control root, field-ownership policy, merge driver",
        prepare=_seed_policy_and_driver,
    )


def _identify(clone: Path, name: str = "Dev", email: str = "dev@example.invalid") -> None:
    identify(clone, name=name, email=email)


def clone(remote: Path, path: Path) -> Path:
    """A working clone of ``remote``, with a git identity and the driver registered."""
    subprocess.run(
        ["git", "clone", "--quiet", str(remote), str(path)],
        check=True, capture_output=True, timeout=60,
    )
    _identify(path)
    register_merge_driver(path)
    return path


def repo_on_bare_remote(tmp_path: Path) -> Tuple[Path, Path]:
    """``(remote, checkout)`` — a bare remote and one clone of it, both hermetic."""
    remote = bare_remote(tmp_path)
    return remote, clone(remote, tmp_path / "work")


def install_policy(root: Path) -> Path:
    """Copy this working copy's REAL committed field-ownership policy into a checkout.

    The shipped policy, not a fixture's idea of one: a policy that exists only in a test
    proves nothing about the branch a merge actually lands on.
    """
    target = Path(root) / POLICY_RELATIVE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((_REPO / POLICY_RELATIVE).read_bytes())
    return target


def register_merge_driver(repo: Path) -> None:
    """Register the projection merge driver exactly as an operator would."""
    git(repo, "config", f"merge.{DRIVER}.name", "ATDD projection merge driver")
    git(repo, "config", f"merge.{DRIVER}.driver",
        f"{sys.executable} -m atdd state merge-projection --base %O --ours %A --theirs %B")
    attributes = repo / ".gitattributes"
    line = f".atdd/state/projection/*.yaml merge={DRIVER}\n"
    existing = attributes.read_text(encoding="utf-8") if attributes.is_file() else ""
    if line not in existing:
        attributes.write_text(existing + line, encoding="utf-8")


def write_evidence(repo: Path, uid: str, tokens: Iterable[str], *, gate: str) -> Path:
    """Commit the evidence a side carries for one gate (``.atdd/evidence/<uid>/<gate>.yaml``).

    Committed, because that is the only evidence a merge can see: the driver reads it out of
    the incoming commit, not out of a store it has no access to (spec §6).

    Sharded per gate, because two developers evidencing two different transitions of one
    object must not collide on the *evidence file* — a merge that conflicts on the evidence
    has failed on the paperwork rather than on the claim.
    """
    path = repo / EVIDENCE_RELATIVE / uid / f"{gate}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(list(tokens)), encoding="utf-8")
    return path


def commit(repo: Path, message: str, *, author: Optional[str] = None) -> str:
    """Commit everything in ``repo``; return the new sha.

    Through ``out``, not the plain fixture runner: this checkout has the projection merge
    driver registered, and the driver has to be able to import ``atdd`` when git invokes it.
    """
    return commit_all(repo, message, author=author, run=out)


def branch(repo: Path, name: str, *, at: Optional[str] = None) -> None:
    git(repo, "checkout", "--quiet", "-b", name, *( [at] if at else [] ))


def checkout_branch(repo: Path, name: str) -> None:
    git(repo, "checkout", "--quiet", name)


def merge(repo: Path, ref: str) -> subprocess.CompletedProcess:
    """``git merge --no-ff`` — the real thing, with the driver registered.

    Returned rather than asserted: whether git conflicted is the acceptance's subject, not
    the harness's business.
    """
    return git(repo, "merge", "--no-ff", "-m", f"merge {ref}", ref, check=False)


def projection_file(repo: Path, uid: str) -> Path:
    return repo / ".atdd" / "state" / "projection" / f"{uid}.yaml"


def head(repo: Path) -> str:
    return out(repo, "rev-parse", "HEAD")
