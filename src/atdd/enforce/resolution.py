# URN: component:enforce-binding-plan:run-binding-plan:provider-resolution:backend:domain
# Runtime: python
# Purpose: Resolve a workspace provider CLI from candidate roots keyed off the
#          lock's workspace_id + contract range — provider-agnostic (D-4).
"""Workspace-provider resolution (#1238 phase ``runner-and-bridge``).

Given candidate roots (where vendored workspace packages live), a target
``workspace_id`` from ``binding.lock.yaml``, and a caret contract range, locate
the matching workspace package and return a handle to its subprocess CLI
(``cli/scan.py``). Resolution is keyed purely off ``workspace_id`` — it is NOT
python-pytest-specific, so a non-python ``workspace_id`` would resolve the same
way (D-4 generality). Core NEVER imports the provider; it reads the provider's
declarative ``atdd.workspace.yaml`` manifest only and then shells out.

The caret rule mirrors the provider's own ``adapter/discover.contract_compatible``:
a range ``^X.Y.Z`` is satisfied by a provider contract ``V`` iff
``major(V) == X`` and ``V >= X.Y.Z`` within that major.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

_log = logging.getLogger(__name__)

WORKSPACE_MANIFEST = "atdd.workspace.yaml"
PROVIDER_CLI_RELPATH = ("cli", "scan.py")

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class ProviderResolutionError(Exception):
    """Base class for any failure to resolve a workspace provider."""


class UnknownWorkspaceError(ProviderResolutionError):
    """No workspace package under the candidate roots declares ``workspace_id``."""


class ContractRangeError(ProviderResolutionError):
    """A matching workspace exists but no version satisfies the contract range."""


class MissingProviderCLIError(ProviderResolutionError):
    """The resolved workspace package has no ``cli/scan.py`` subprocess entrypoint."""


class InvalidContractSpecError(ProviderResolutionError):
    """``requires_contract`` is not a parseable caret SemVer range."""


@dataclass(frozen=True)
class ResolvedProvider:
    """A resolved, contract-compatible workspace provider.

    ``provider_cli_path`` is the subprocess boundary core invokes.
    """

    workspace_id: str
    provider_cli_path: Path
    contract_version: str


def _parse_semver(value: str) -> tuple[int, int, int]:
    m = _SEMVER.match(str(value or "").strip())
    if not m:
        raise ValueError(f"invalid SemVer {value!r}; expected MAJOR.MINOR.PATCH")
    return tuple(int(g) for g in m.groups())  # type: ignore[return-value]


def _parse_caret_base(requires_contract: str) -> tuple[int, int, int]:
    spec = str(requires_contract or "").strip()
    if spec.startswith("^"):
        spec = spec[1:].strip()
    try:
        return _parse_semver(spec)
    except ValueError as exc:
        raise InvalidContractSpecError(
            f"invalid requires_contract {requires_contract!r}; "
            f"expected a caret range like '^1.0.0'"
        ) from exc


def contract_satisfies(provider_version: str, requires_contract: str) -> bool:
    """True if ``provider_version`` satisfies the caret ``requires_contract`` range."""
    bmaj, bmin, bpat = _parse_caret_base(requires_contract)
    try:
        pmaj, pmin, ppat = _parse_semver(provider_version)
    except ValueError as exc:
        # A malformed provider version is treated as incompatible (one bad
        # manifest can't sink resolution) — surfaced so it is not silent.
        _log.warning(
            "ignoring malformed provider contract_version",
            extra={"contract_version": str(provider_version), "error": str(exc)},
        )
        return False
    return pmaj == bmaj and (bmin, bpat) <= (pmin, ppat)


@dataclass(frozen=True)
class _WorkspaceManifest:
    workspace_id: str
    contract_version: str
    workspace_dir: Path
    manifest_path: Path


def _iter_workspace_manifests(
    candidate_roots: Iterable[str | Path],
) -> list[_WorkspaceManifest]:
    """Find every well-formed workspace manifest under the candidate roots."""
    seen: set[Path] = set()
    found: list[_WorkspaceManifest] = []
    for raw_root in candidate_roots:
        root = Path(raw_root)
        if not root.is_dir():
            continue
        for manifest_path in sorted(root.rglob(WORKSPACE_MANIFEST)):
            resolved = manifest_path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                data = yaml.safe_load(manifest_path.read_text()) or {}
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(data, dict) or data.get("kind") != "workspace":
                continue
            workspace_id = data.get("workspace_id")
            contract_version = data.get("contract_version")
            if not workspace_id or not contract_version:
                continue
            found.append(
                _WorkspaceManifest(
                    workspace_id=str(workspace_id),
                    contract_version=str(contract_version),
                    workspace_dir=manifest_path.parent,
                    manifest_path=manifest_path,
                )
            )
    return found


def resolve_provider(
    candidate_roots: Iterable[str | Path],
    workspace_id: str,
    requires_contract: str = "^1.0.0",
) -> ResolvedProvider:
    """Resolve a workspace provider to a subprocess-CLI handle.

    When several compatible versions are installed, the highest contract version
    wins. Raises a :class:`ProviderResolutionError` subclass on any failure.
    """
    _parse_caret_base(requires_contract)
    manifests = _iter_workspace_manifests(candidate_roots)

    matches = [m for m in manifests if m.workspace_id == workspace_id]
    if not matches:
        available = sorted({m.workspace_id for m in manifests})
        raise UnknownWorkspaceError(
            f"workspace_id {workspace_id!r} not found under candidate roots; "
            f"available: {available or '(none)'}"
        )

    compatible = [
        m for m in matches if contract_satisfies(m.contract_version, requires_contract)
    ]
    if not compatible:
        offered = sorted(m.contract_version for m in matches)
        raise ContractRangeError(
            f"workspace {workspace_id!r} found, but no installed contract version "
            f"satisfies {requires_contract!r}; offered: {offered}"
        )

    best = max(compatible, key=lambda m: _parse_semver(m.contract_version))
    cli_path = best.workspace_dir.joinpath(*PROVIDER_CLI_RELPATH)
    if not cli_path.is_file():
        raise MissingProviderCLIError(
            f"workspace {workspace_id!r} (contract {best.contract_version}) resolved "
            f"at {best.workspace_dir}, but its provider CLI is missing: {cli_path}"
        )

    return ResolvedProvider(
        workspace_id=best.workspace_id,
        provider_cli_path=cli_path,
        contract_version=best.contract_version,
    )
