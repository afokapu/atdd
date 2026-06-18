"""Substrate admission orchestration (WMBTs C001/C002/C003/E001/C004).

`admit()` is the core of `atdd add`: resolve a package, validate its manifest +
owned files + realizes/depends_on against core (reusing the package-composition
seam read-only), compose an in-memory protocol view, record a sha256 digest, and
install into a versioned `.atdd/` home — writing intent + lock.

INVARIANT (C001): admission NEVER imports or executes an extension implementation
module. It inspects manifests and composes pure data only; `executed_implementations`
is always empty. Runtime binding is a later, separate wagon.

RED: `admit` is an unimplemented stub; C001's tests fail until GREEN ships the
non-executing admission path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AdmissionResult:
    """Outcome of admitting one package, without executing any of its code."""

    package_id: str
    kind: str
    installed_path: Path | None = None
    digest: str | None = None
    composed: dict = field(default_factory=dict)
    # Always empty: admission never runs an extension implementation.
    executed_implementations: list = field(default_factory=list)


def inspect_package(package_dir: str | Path) -> dict:
    """Load a package manifest WITHOUT importing any of its code. (GREEN)"""
    raise NotImplementedError("C003: inspect_package not implemented (RED)")


def validate_and_compose(
    package_dir: str | Path, *, core_ids: "set[str] | None" = None
) -> AdmissionResult:
    """Validate a package and compose its protocol view — NO install, NO execution.

    Resolve → validate manifest + owned files → validate realizes/depends_on →
    compose protocol view. Returns an AdmissionResult whose
    ``executed_implementations`` is always empty: this path reads manifests and
    composes pure data and must never import an implementation module. Raises on
    any validation failure. (GREEN)
    """
    raise NotImplementedError("C001/C003: validate_and_compose not implemented (RED)")


def admit(
    package_dir: str | Path,
    *,
    project_root: str | Path,
    core_ids: "set[str] | None" = None,
) -> AdmissionResult:
    """Validate + compose + install a package without executing its code. (GREEN)

    Resolve → validate manifest + owned files → validate realizes/depends_on →
    compose protocol view → sha256 digest → install into `.atdd/{kind}s/<id>/<version>/`
    → write substrate intent + lock. Refuses (raises) on any validation failure,
    leaving the substrate unchanged. Never imports an implementation module.
    """
    raise NotImplementedError("C001/C003/E001: admit not implemented (RED)")
