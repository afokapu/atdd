# URN: component:isolate-provider-boundary:test-support:seam_fixtures:backend:tests
# Runtime: python
# Purpose: Conforming, failing and rogue SyncProvider implementations plus synthetic core packages, so the boundary can be tested from the outside — as an extension author would meet it.

"""Provider and package fixtures for the isolate-provider-boundary acceptances (#1400).

Every provider here is written the way a real extension is written: **it does not import core.**
It duck-types the seam. That is not stylistic — a provider that imported ``atdd`` to subclass
something would be testing the boundary in the one direction the law permits and leaving the
other direction (the one that actually matters) unexercised. If these stubs satisfy the Protocol
without ever importing it, so can a real extension in its own repository.

The synthetic *core* packages are the mirror image: real directories with real ``.py`` files that
import a provider, shell out to ``gh``, or import something that does not exist on this machine at
all. The guard is asked to judge them from source, and the last of those is the one that proves it
is judging from source — a check that imported what it inspects would report "clean" for a package
whose only sin is a dependency that is not installed.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from atdd.state.projection import PROJECTION_RELATIVE, canonical_bytes

#: Pinned uids, so a fixture's bytes never move between runs.
UID_X = "wi_01HF7YAT00M78607F0000000X1"
UID_Y = "wi_01HF7YAT00M78607F0000000Y2"


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
    """A projection keyed by uid — the shape the seam takes."""
    return {str(doc["uid"]): dict(doc) for doc in documents}


def write_projection(root: Path, documents: Sequence[Mapping[str, Any]]) -> Path:
    """Write documents as a repo's committed projection, in canonical bytes."""
    out = Path(root) / PROJECTION_RELATIVE
    out.mkdir(parents=True, exist_ok=True)
    for doc in documents:
        (out / f"{doc['uid']}.yaml").write_bytes(canonical_bytes(doc))
    return out


# --------------------------------------------------------------------------- #
# Providers — duck-typed, and none of them imports core
# --------------------------------------------------------------------------- #
@dataclass
class Ref:
    """What a provider hands back. Deliberately NOT core's ExternalRefUpdate class.

    A real extension constructs its own record and the seam validates the shape. If these tests
    used core's dataclass, they would be testing that core can read its own types.
    """

    uid: str
    provider: str
    namespace: str
    ref_kind: str
    ref_value: str
    authoritative: bool = False


@dataclass
class Alarm:
    """A drift record, likewise duck-typed."""

    uid: str
    provider: str
    kind: str
    detail: str = ""
    authoritative: bool = False
    claims: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class Stamp:
    """An ExtensionDigest, duck-typed."""

    name: str
    version: str
    digest: str


@dataclass
class StubProvider:
    """A conforming provider. Records what it was shown, so "never invoked" is checkable."""

    name: str = "demo"
    version: str = "1.0.0"
    refs: List[Ref] = field(default_factory=list)
    alarms: List[Alarm] = field(default_factory=list)
    body: str = "v1"
    #: Every snapshot list it was handed — empty means it was never invoked.
    seen: List[Sequence[Any]] = field(default_factory=list)

    def mirror(self, objects: Sequence[Any]) -> List[Ref]:
        self.seen.append(list(objects))
        if self.refs:
            return list(self.refs)
        return [
            Ref(uid=snapshot.uid, provider=self.name, namespace=f"bot:{self.name}",
                ref_kind="issue_number", ref_value=f"{1400 + index}")
            for index, snapshot in enumerate(objects)
        ]

    def detect_drift(self, objects: Sequence[Any]) -> List[Alarm]:
        return list(self.alarms)

    def digest(self) -> Stamp:
        return Stamp(
            name=self.name, version=self.version,
            digest="sha256:" + hashlib.sha256(self.body.encode("utf-8")).hexdigest(),
        )


@dataclass
class FailingProvider:
    """A provider whose ``mirror()`` raises. The mirror is presentation; this must not be a gate."""

    name: str = "broken"
    version: str = "9.9.9"
    boom: str = "the GitHub API returned 503"
    invoked: int = 0

    def mirror(self, objects: Sequence[Any]) -> List[Ref]:
        self.invoked += 1
        raise RuntimeError(self.boom)

    def detect_drift(self, objects: Sequence[Any]) -> List[Alarm]:
        raise RuntimeError(self.boom)

    def digest(self) -> Stamp:
        return Stamp(name=self.name, version=self.version, digest="sha256:" + "0" * 64)


def factory(provider: Any):
    """A zero-arg factory over an already-built provider (the registry's registration unit)."""
    return lambda: provider


# --------------------------------------------------------------------------- #
# Synthetic core packages — for the guard to judge from source
# --------------------------------------------------------------------------- #
def core_package(root: Path, modules: Optional[Mapping[str, str]] = None) -> Path:
    """A minimal but REAL ``atdd``-shaped package the import guard can walk.

    ``atdd/state/<module>.py`` for each lifecycle module the guard looks for. Whatever the caller
    does not supply is written clean, so an offender is the only thing that differs from a package
    that passes — the acceptance then fails about the offender and about nothing else.
    """
    package = Path(root) / "atdd"
    (package / "state").mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "state" / "__init__.py").write_text("", encoding="utf-8")
    for name, source in (modules or {}).items():
        (package / "state" / f"{name}.py").write_text(source, encoding="utf-8")
    return package


#: A core module that imports a provider package. The package is NOT installed anywhere — which is
#: the point: a guard that imported what it inspects would call this clean.
IMPORTS_PROVIDER = "import github\n\n\ndef decide():\n    return github.Issue\n"

#: A core module that shells out to `gh`. No import to find; an import-only guard sails past it.
SHELLS_OUT_TO_GH = (
    "import subprocess\n\n\n"
    "def decide():\n"
    '    return subprocess.run(["gh", "issue", "view", "1400"], check=True)\n'
)

#: A core module that reads an issue number as a code identifier (not as projection data).
READS_ISSUE_NUMBER = (
    "def decide(work_item):\n"
    "    issue_number = work_item.issue_number\n"
    "    return issue_number > 0\n"
)

#: A core module that imports the provider REGISTRY — so a lifecycle decision could consult it.
IMPORTS_REGISTRY = (
    "from atdd.state.provider_seam import discover_providers\n\n\n"
    "def decide():\n"
    "    return bool(discover_providers())\n"
)

#: A clean lifecycle module that reaches a provider only THROUGH a core helper it imports. The
#: whole reason the walk is transitive.
IMPORTS_A_HELPER = "from atdd.state.helper import decide  # noqa: F401\n"
HELPER_IMPORTS_PROVIDER = "import requests\n\n\ndef decide():\n    return requests.get\n"

#: A module that raises the moment it is imported. The guard must scan it exactly the same.
EXPLODES_ON_IMPORT = "raise RuntimeError('importing me is a bug')\n\nimport github  # noqa: E402\n"
