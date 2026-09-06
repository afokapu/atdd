"""The substrate coherence invariant (#1488).

    No rule bound in `binding.lock.yaml` may reference a package that
    `substrate.lock.yaml` says is not installed.

`substrate.lock.yaml` (what is installed) and `binding.lock.yaml` (what those
installs are allowed to enforce) are two projections of ONE substrate: the binder
DERIVES the second from the first. When a command updates one and not the other
the pair does not go stale, it goes SPLIT-BRAIN — `atdd enforce` reads the binding
lock, and will run rules from a package the substrate lock says was uninstalled.

`atdd substrate remove --prune` did exactly that: it dropped the substrate-lock
entry, left the package on disk with its rules bound, and printed `removed <ref>`.
Stating the invariant once, here, lets a command VERIFY its own postcondition
instead of asserting it — which is the difference between reporting success and
achieving it.

A bound entry that names no owning package is a violation too. A binding that
cannot be attributed to an installed package cannot be shown to satisfy the
invariant, and for the artifact that decides what enforces a repo, unprovable is
not good enough. The remedy is a re-`bind`, which the message says.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

BINDING_LOCK = "binding.lock.yaml"
BOUND = "bound"


@dataclass(frozen=True)
class CoherenceViolation:
    """One bound rule that the substrate lock cannot account for."""

    convention_id: str
    reason: str
    missing_package: str | None = None

    def __str__(self) -> str:
        return f"{self.convention_id}: {self.reason}"


class IncoherentSubstrateError(ValueError):
    """binding.lock.yaml binds rules that substrate.lock.yaml cannot account for."""

    def __init__(self, violations: "list[CoherenceViolation]") -> None:
        self.violations = list(violations)
        detail = "; ".join(str(v) for v in self.violations)
        super().__init__(
            f"{len(self.violations)} rule(s) bound to a package absent from the "
            f"substrate: {detail}"
        )


def _installed_ids(project_root: str | Path) -> set[str]:
    from atdd.substrate import installer

    return {a["id"] for a in installer.list_substrate(project_root) if a.get("id")}


def _bound_entries(project_root: str | Path) -> list[dict]:
    path = Path(project_root) / ".atdd" / BINDING_LOCK
    if not path.exists():
        return []  # nothing was ever bound; nothing can be orphaned
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [c for c in (data.get("conventions") or []) if c.get("disposition") == BOUND]


def _entry_violations(entry: dict, installed: set[str]) -> list[CoherenceViolation]:
    """The ways one bound entry can disagree with the substrate lock."""
    rule = entry.get("convention_id", "<unknown>")
    package = entry.get("package_id")
    if not package:
        return [
            CoherenceViolation(
                rule,
                "bound, but records no owning package_id, so it cannot be "
                "attributed to an installed package — re-run `atdd substrate bind`",
            )
        ]

    found: list[CoherenceViolation] = []
    if package not in installed:
        found.append(
            CoherenceViolation(
                rule,
                f"bound to package {package!r}, which is not installed per "
                "substrate.lock.yaml",
                package,
            )
        )
    workspace = entry.get("workspace_id")
    if workspace and workspace not in installed:
        found.append(
            CoherenceViolation(
                rule,
                f"bound to workspace {workspace!r}, which is not installed per "
                "substrate.lock.yaml",
                workspace,
            )
        )
    return found


def check_coherence(project_root: str | Path) -> list[CoherenceViolation]:
    """Every bound rule that references a package the substrate lock does not carry.

    An empty list means the two locks agree. `legacy-fallback` entries reference no
    package and so cannot violate the invariant.
    """
    installed = _installed_ids(project_root)
    violations: list[CoherenceViolation] = []
    for entry in _bound_entries(project_root):
        violations.extend(_entry_violations(entry, installed))
    return violations


def assert_coherent(project_root: str | Path) -> None:
    """Raise `IncoherentSubstrateError` unless the two locks agree."""
    violations = check_coherence(project_root)
    if violations:
        raise IncoherentSubstrateError(violations)
