"""The bare-remote fixture: a git remote that is object storage and nothing else (#1400 §8).

Core's central claim is that the whole lifecycle is satisfiable by ``git`` alone — no GitHub,
no API, no provider (I7, spec §2.2). The way that claim is tested, everywhere it is tested, is
to build a **bare** remote and run against it: bare on purpose, because there is then no remote
API to call even if a step wanted to, and a suite that proved this against a GitHub remote with
the calls merely mocked out would have proved that the mocks work.

That fixture is what this module is. It was previously spelled out once in the conformance
suite and once again in each live acceptance harness — five copies of the same twelve lines,
differing only in what else they seeded and what they called the commit. Five copies of a
fixture is five chances for one of them to stop being the thing the others are testing.

:func:`seed_bare_remote` is the whole fixture; :func:`clone_of` and :func:`identify` build the
working checkouts; :func:`write_gh_shim` arms the ``gh`` tripwire that catches a shell-out from
anywhere in a run, including from inside a git subprocess.

Dependency discipline: stdlib only (never a provider).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Optional, Tuple

#: What a Control Root never shares. The store is the private authoring workspace (spec §2.1);
#: ``version_cache.json`` is the CLI's per-checkout upgrade-check cache. Committing either would
#: push one developer's private state at another.
STORE_GITIGNORE = ".atdd/state/state.sqlite*\n.atdd/version_cache.json\n"

#: What the ``gh`` shim says on stderr when something reaches for it.
GH_UNAVAILABLE = "gh is not available: core runs against a bare remote"


class ConformanceError(RuntimeError):
    """The fixture could not be set up (a git fault, not a gate failure)."""


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=180,
    )
    if check and result.returncode != 0:
        raise ConformanceError(f"git {' '.join(args)} failed in {repo}: {result.stderr.strip()}")
    return result.stdout.strip()


def identify(repo: Path, *, name: str = "Dev", email: str = "dev@example.invalid") -> None:
    """Pin a git identity, so a fixture's commits never depend on the developer's config."""
    git(repo, "config", "user.email", email)
    git(repo, "config", "user.name", name)


def clone_of(remote: Path, path: Path) -> Path:
    """A working clone of ``remote`` with a pinned git identity."""
    subprocess.run(
        ["git", "clone", "--quiet", str(remote), str(path)],
        check=True, capture_output=True, timeout=60,
    )
    identify(path)
    return path


def seed_bare_remote(
    root: Path,
    *,
    gitignore: str = STORE_GITIGNORE,
    message: str = "seed: control root + empty projection",
    prepare: Optional[Callable[[Path], None]] = None,
) -> Path:
    """A bare remote carrying ``main``, seeded with a Control Root and an empty projection.

    ``prepare`` runs against the seed checkout after the Control Root exists and before the
    seed commit, for whatever else a caller needs committed on ``main`` (a field-ownership
    policy, a merge driver).
    """
    root = Path(root)
    remote = root / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", "--quiet", "--initial-branch=main", str(remote)],
        check=True, capture_output=True, timeout=60,
    )
    seed = root / "seed"
    subprocess.run(
        ["git", "clone", "--quiet", str(remote), str(seed)],
        check=True, capture_output=True, timeout=60,
    )
    identify(seed)
    (seed / ".atdd" / "state" / "projection").mkdir(parents=True, exist_ok=True)
    (seed / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    (seed / ".atdd" / "state" / "projection" / ".gitkeep").write_text("", encoding="utf-8")
    (seed / ".gitignore").write_text(gitignore, encoding="utf-8")
    if prepare is not None:
        prepare(seed)
    git(seed, "add", "-A")
    git(seed, "commit", "--quiet", "-m", message)
    git(seed, "push", "--quiet", "origin", "main")
    return remote


def write_gh_shim(root: Path, *, message: str = GH_UNAVAILABLE) -> Tuple[Path, Path]:
    """A ``gh`` that cannot work, in ``root/tripwire-bin``; it notes any call and exits non-zero.

    Returns ``(bin_dir, marker)``. The marker's *absence* after a run is the assertion: not
    "gh returned nothing useful" but "gh was never reached for".
    """
    bin_dir = Path(root) / "tripwire-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    marker = bin_dir / "gh-was-invoked"
    shim = bin_dir / "gh"
    shim.write_text(
        '#!/bin/sh\necho "$@" >> "$(dirname "$0")/gh-was-invoked"\n'
        f'echo "{message}" >&2\nexit 127\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return bin_dir, marker
