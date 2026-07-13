# URN: component:isolate-provider-boundary:test-support:live_cli:backend:tests
# Runtime: python
# Purpose: Drive the real in-tree `atdd state` CLI by subprocess against real checkouts of a real bare (non-GitHub) remote, with a real extension provider package installed on PYTHONPATH and a `gh` tripwire first on PATH.

"""Live-CLI harness for the isolate-provider-boundary SMOKE acceptances (#1400).

Three things here are real, and the third is the one that makes the wagon's claim checkable.

The **remote** is bare: ``git init --bare``. Git object storage, no GitHub, no API, no token. Every
lifecycle claim these acceptances make is made against a remote that could not answer an API call
if core tried one — so "core does not depend on GitHub" is a property of the fixture rather than a
line in a docstring.

The **CLI** is this working copy's, driven by ``python -m atdd state ...`` in a subprocess. Not the
functions the CLI happens to call: the command, with its argument parsing and its exit codes, which
is what CI actually runs.

The **extension** is a real package in a real directory, installed onto the subprocess's
``PYTHONPATH`` and registered through the composition root (``--provider pkg:factory``). It never
imports ``atdd``. Core never imports it. That is the boundary law with both halves present, which
is the only way to find out whether the seam is wide enough to be satisfied and narrow enough to
be safe.

And a ``gh`` **tripwire** goes first on ``PATH`` in every subprocess: a shim that records its
arguments and exits 127. If any command in any of these runs reaches for the GitHub CLI, the run
does not quietly succeed — the marker file says so.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

#: The in-tree ``src/`` root, so every subprocess drives THIS working copy's CLI.
_SRC = Path(__file__).resolve().parents[4]

#: The repository root.
_REPO = Path(__file__).resolve().parents[5]


def gh_tripwire(root: Path) -> Tuple[Path, Path]:
    """A ``gh`` on ``PATH`` that cannot work and leaves a note if anyone calls it.

    Returns ``(bin_dir, marker)``. The marker's *absence* after a run is the assertion: not "gh
    returned nothing useful" but "gh was never reached for".
    """
    bin_dir = Path(root) / "tripwire-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    marker = bin_dir / "gh-was-invoked"
    shim = bin_dir / "gh"
    shim.write_text(
        '#!/bin/sh\necho "$@" >> "$(dirname "$0")/gh-was-invoked"\n'
        'echo "gh is not available" >&2\nexit 127\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return bin_dir, marker


def env(root: Path, *, extension: Optional[Path] = None) -> dict:
    """The subprocess environment: this working copy's ``src``, a hermetic HOME, a ``gh`` tripwire.

    ``extension`` puts a real provider package on ``PYTHONPATH`` — *alongside* core, never inside
    it. An extension core could only see by being vendored into its own tree would not be an
    extension.
    """
    bin_dir, _marker = gh_tripwire(root)
    path = [str(bin_dir), os.environ.get("PATH", "")]
    python_path = [str(_SRC)] + ([str(extension)] if extension else [])
    return {
        "PYTHONPATH": os.pathsep.join(python_path),
        "PATH": os.pathsep.join(part for part in path if part),
        "HOME": str(root),
        "CI": "true",
    }


def atdd_state(
    root: Path, *args: str, extension: Optional[Path] = None, cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess:
    """Run ``atdd state <args> --root <root>`` and capture its result."""
    return subprocess.run(
        [sys.executable, "-m", "atdd", "state", *args, "--root", str(root)],
        cwd=str(cwd or root), env=env(root, extension=extension),
        capture_output=True, text=True, timeout=300,
    )


def gh_was_invoked(root: Path) -> List[str]:
    """Every ``gh`` invocation the tripwire caught during the runs rooted at ``root``."""
    _bin, marker = gh_tripwire(root)
    if not marker.is_file():
        return []
    return [line.strip() for line in marker.read_text(encoding="utf-8").splitlines() if line.strip()]


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=str(repo), env={**os.environ, **env(repo)},
        capture_output=True, text=True, timeout=180,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stdout}{result.stderr}")
    return result


def out(repo: Path, *args: str) -> str:
    return git(repo, *args).stdout.strip()


def bare_remote(tmp_path: Path) -> Path:
    """A bare git remote carrying ``main``: git object storage and nothing else."""
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", "--quiet", "--initial-branch=main", str(remote)],
        check=True, capture_output=True, timeout=60,
    )
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "--quiet", str(remote), str(seed)],
                   check=True, capture_output=True, timeout=60)
    _identify(seed)
    (seed / ".atdd" / "state" / "projection").mkdir(parents=True, exist_ok=True)
    (seed / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    (seed / ".atdd" / "state" / "projection" / ".gitkeep").write_text("", encoding="utf-8")
    (seed / ".gitignore").write_text(
        ".atdd/state/state.sqlite*\n.atdd/version_cache.json\ntripwire-bin/\n", encoding="utf-8")
    install_policy(seed)
    git(seed, "add", "-A")
    git(seed, "commit", "--quiet", "-m", "seed: control root, field-ownership policy")
    git(seed, "push", "--quiet", "origin", "main")
    return remote


def install_policy(root: Path) -> Path:
    """Copy this working copy's REAL committed field-ownership policy into a checkout.

    The shipped policy, not a fixture's idea of one. The field-writer gate is what admits the bot's
    ``external_refs`` write, and it judges by the table the repository actually commits — so a
    checkout that carried a made-up policy would be proving the seam agrees with a fiction.
    """
    from atdd.state.ownership import POLICY_RELATIVE

    target = Path(root) / POLICY_RELATIVE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((_REPO / POLICY_RELATIVE).read_bytes())
    return target


def _identify(clone: Path, name: str = "Dev", email: str = "dev@example.invalid") -> None:
    git(clone, "config", "user.email", email)
    git(clone, "config", "user.name", name)


def clone(remote: Path, path: Path) -> Path:
    subprocess.run(["git", "clone", "--quiet", str(remote), str(path)],
                   check=True, capture_output=True, timeout=60)
    _identify(path)
    return path


def repo_on_bare_remote(tmp_path: Path) -> Tuple[Path, Path]:
    """``(remote, checkout)`` — a bare remote and one clone of it, both hermetic."""
    remote = bare_remote(tmp_path)
    return remote, clone(remote, tmp_path / "work")


def commit(repo: Path, message: str, *, author: Optional[str] = None) -> str:
    git(repo, "add", "-A")
    args = ["commit", "--quiet", "--allow-empty", "-m", message]
    if author is not None:
        args += ["--author", author]
    git(repo, *args)
    return out(repo, "rev-parse", "HEAD")


def projection_file(repo: Path, uid: str) -> Path:
    return repo / ".atdd" / "state" / "projection" / f"{uid}.yaml"


# --------------------------------------------------------------------------- #
# A REAL extension package — on disk, importable, and it never imports core
# --------------------------------------------------------------------------- #
#: The provider an extension repository would ship. Note what is absent: any ``import atdd``.
#: It satisfies the seam structurally, which is the only way a provider in another repository
#: could satisfy it at all.
EXTENSION_SOURCE = '''\
"""A real extension provider. It imports core NOWHERE — it duck-types the seam (spec §8.1)."""
from dataclasses import dataclass, field
from typing import Any, List, Mapping, Sequence

VERSION = "2.1.0"
DIGEST = "sha256:" + "ab" * 32


@dataclass
class Ref:
    uid: str
    provider: str
    namespace: str
    ref_kind: str
    ref_value: str
    authoritative: bool = False


@dataclass
class Alarm:
    uid: str
    provider: str
    kind: str
    detail: str = ""
    authoritative: bool = False
    claims: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class Stamp:
    name: str
    version: str
    digest: str


class DemoProvider:
    name = "demo"

    def mirror(self, objects: Sequence[Any]) -> List[Ref]:
        return [
            Ref(uid=obj.uid, provider="demo", namespace="bot:demo",
                ref_kind="issue_number", ref_value=str(1400 + index))
            for index, obj in enumerate(objects)
        ]

    def detect_drift(self, objects: Sequence[Any]) -> List[Alarm]:
        return []

    def digest(self) -> Stamp:
        return Stamp(name="demo", version=VERSION, digest=DIGEST)


def make() -> DemoProvider:
    return DemoProvider()
'''

#: The same extension, but its mirror raises. A broken mirror may not block a merge (I7).
BROKEN_EXTENSION_SOURCE = EXTENSION_SOURCE.replace(
    "    def mirror(self, objects: Sequence[Any]) -> List[Ref]:\n"
    "        return [\n"
    "            Ref(uid=obj.uid, provider=\"demo\", namespace=\"bot:demo\",\n"
    "                ref_kind=\"issue_number\", ref_value=str(1400 + index))\n"
    "            for index, obj in enumerate(objects)\n"
    "        ]\n",
    "    def mirror(self, objects: Sequence[Any]) -> List[Ref]:\n"
    "        raise RuntimeError('the GitHub API returned 503')\n",
)

#: An extension that tries to write a lifecycle field by returning a non-bot-namespaced ref.
ROGUE_EXTENSION_SOURCE = EXTENSION_SOURCE.replace('namespace="bot:demo"', 'namespace="human"')

#: The provider spec the composition root takes: ``module:factory``. Core imports the STRING.
EXTENSION_SPEC = "atdd_ext_demo:make"


def install_extension(tmp_path: Path, source: str = EXTENSION_SOURCE, *, name: str = "ext") -> Path:
    """Write a real, importable extension package and return the dir to put on ``PYTHONPATH``."""
    root = Path(tmp_path) / name
    root.mkdir(parents=True, exist_ok=True)
    (root / "atdd_ext_demo.py").write_text(source, encoding="utf-8")
    return root


def seed_object(
    repo: Path, *, extension: Optional[Path] = None, body: str = "Author feature-x.",
) -> str:
    """Mint a real object in a real store and project it — the real CLI, the real sqlite.

    Returns the uid. The body is not decoration: the ∅->INIT gate demands ``body_initialized``
    (spec §6), so an object authored without one could not legally be committed at all.
    """
    created = atdd_state(repo, "object", "create", "--slug", "feature-x", "--owner", "dev-a",
                         "--title", "Feature X", "--body", body, extension=extension)
    assert created.returncode == 0, created.stdout + created.stderr
    uid = created.stdout.strip().splitlines()[-1].strip()
    projected = atdd_state(repo, "project", extension=extension)
    assert projected.returncode == 0, projected.stdout + projected.stderr
    return uid


def commit_projection(repo: Path, uid: str, *, author: Optional[str] = None) -> str:
    """Commit the projected object with the trailers the ∅->INIT gate demands (spec §5, §6).

    Committing is not optional bookkeeping. A freshly authored object is *uncommitted overlay*, and
    core refuses to hydrate over it — correctly, since hydration is the overwrite path and the work
    would be lost (I5). The way to share private work is to project it, commit it, and push it.
    """
    import yaml

    from atdd.state.projection import object_digest

    document = yaml.safe_load(projection_file(repo, uid).read_text(encoding="utf-8"))
    return commit(repo, "\n".join([
        "feat: author feature-x",
        "",
        f"ATDD-Object: {uid}",
        f"ATDD-Projection-Digest: {object_digest(document)}",
    ]), author=author)
