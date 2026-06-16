# Component: component:author-atdd-substrate:substrate-spine:AuthorManifest:backend:application
"""Package-manifest validators + the provider↔implementation contract (C006).

Validate the three package manifests — extension (`atdd.extension.yaml`),
workspace provider (`atdd.workspace.yaml`), and implementation
(`atdd.implementation.yaml`) — and the versioned CONTRACT that ties them
together: a provider declares a concrete ``contract_version``; an extension and
an implementation declare the range/version they target; the resolver checks
SemVer compatibility and refuses on mismatch.

Reuses the namespace guards (``validate_extension_id`` / ``validate_workspace_id``)
so an id is never validated two different ways.
"""
from __future__ import annotations

import re

from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_context import (
    validate_extension_id,
    validate_workspace_id,
)

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
# Supported ranges: exact (1.0.0), caret (^1.0.0), tilde (~1.0.0), >= (>=1.0.0),
# and x-ranges (1.x / 1.2.x). Compound ranges are intentionally unsupported in V1.
_RANGE_RE = re.compile(
    r"^(?P<op>\^|~|>=|=)?\s*(?P<maj>\d+)\.(?P<min>\d+|x|\*)(?:\.(?P<pat>\d+|x|\*))?$"
)
_RUNTIME_KEYS = ("language", "runner", "command")


def _parse_version(value, *, field: str = "contract_version") -> tuple[int, int, int]:
    m = _SEMVER_RE.match(str(value or ""))
    if not m:
        raise AuthorInputError(
            field, f"invalid version {value!r}; expected concrete MAJOR.MINOR.PATCH"
        )
    return tuple(int(x) for x in m.groups())  # type: ignore[return-value]


def _parse_range(spec, *, field: str = "contract") -> re.Match:
    m = _RANGE_RE.match(str(spec or "").strip())
    if not m:
        raise AuthorInputError(
            field,
            f"invalid contract range {spec!r}; expected e.g. ^1.0.0, ~1.2.0, 1.0.0, 1.x",
        )
    return m


def contract_satisfies(version: str, spec: str) -> bool:
    """True if concrete SemVer ``version`` satisfies range ``spec``.

    Supports exact (``1.0.0``), caret (``^1.0.0`` — same major, ≥ base), tilde
    (``~1.0.0`` — same major+minor, ≥ base), ``>=``, and x-ranges (``1.x`` /
    ``1.2.x``). Raises ``AuthorInputError`` if either side is malformed.
    """
    cur = _parse_version(version)
    m = _parse_range(spec)
    op = m.group("op") or "="
    rmaj = int(m.group("maj"))
    rmin_raw, rpat_raw = m.group("min"), m.group("pat")

    if rmin_raw in ("x", "*"):
        return cur[0] == rmaj
    rmin = int(rmin_raw)
    if rpat_raw in ("x", "*"):
        return cur[0] == rmaj and cur[1] == rmin
    base = (rmaj, rmin, int(rpat_raw) if rpat_raw is not None else 0)

    if op == ">=":
        return cur >= base
    if op == "^":
        return cur[0] == rmaj and cur >= base
    if op == "~":
        return cur[0] == rmaj and cur[1] == rmin and cur >= base
    return cur == base  # exact


def validate_workspace_manifest(data: dict) -> None:
    """Validate an ``atdd.workspace.yaml`` provider manifest."""
    if (data or {}).get("kind") != "workspace":
        raise AuthorInputError("kind", "workspace manifest must have kind: workspace")
    validate_workspace_id(data.get("workspace_id", ""), allow_reserved=True)
    _parse_version(data.get("contract_version"))
    runtime = data.get("runtime") or {}
    for key in _RUNTIME_KEYS:
        if not runtime.get(key):
            raise AuthorInputError("runtime", f"workspace runtime missing {key!r}")
    discovers = data.get("discovers") or {}
    if not discovers.get("implementations"):
        raise AuthorInputError("discovers", "workspace must declare discovers.implementations")
    if discovers.get("requires_contract") is not None:
        _parse_range(discovers["requires_contract"], field="requires_contract")


def validate_extension_manifest(data: dict) -> None:
    """Validate an ``atdd.extension.yaml`` use-case manifest."""
    if (data or {}).get("kind") != "extension":
        raise AuthorInputError("kind", "extension manifest must have kind: extension")
    validate_extension_id(data.get("extension_id", ""), allow_reserved=True)
    if not isinstance(data.get("owns"), dict):
        raise AuthorInputError("owns", "extension manifest must have an owns mapping")
    for entry in ((data.get("depends_on") or {}).get("workspaces") or []):
        if not isinstance(entry, dict):
            raise AuthorInputError(
                "depends_on", "each depends_on.workspaces entry must be a mapping {id, contract}"
            )
        validate_workspace_id(entry.get("id", ""), allow_reserved=True)
        _parse_range(entry.get("contract"), field="depends_on")


def validate_implementation_manifest(data: dict) -> None:
    """Validate an ``atdd.implementation.yaml`` manifest."""
    if (data or {}).get("kind") != "implementation":
        raise AuthorInputError("kind", "implementation manifest must have kind: implementation")
    if not data.get("implementation_id"):
        raise AuthorInputError("implementation_id", "implementation manifest missing implementation_id")
    validate_workspace_id(data.get("targets_workspace", ""), allow_reserved=True)
    _parse_version(data.get("contract_version"))


def extension_targets_satisfied_by(ext_manifest: dict, provider_manifest: dict) -> bool:
    """True if the provider's contract_version satisfies the extension's range for it."""
    pid = provider_manifest.get("workspace_id")
    pver = provider_manifest.get("contract_version")
    for entry in ((ext_manifest.get("depends_on") or {}).get("workspaces") or []):
        if entry.get("id") == pid and not contract_satisfies(pver, entry.get("contract")):
            return False
    return True


def implementation_accepted_by(impl_manifest: dict, provider_manifest: dict) -> bool:
    """True if the implementation's contract_version satisfies the provider's requires_contract."""
    req = (provider_manifest.get("discovers") or {}).get("requires_contract")
    if not req:
        return True
    return contract_satisfies(impl_manifest.get("contract_version"), req)
