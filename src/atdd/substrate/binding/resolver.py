"""Workspace resolution + SemVer contract check (WMBT C002).

Each implementation declares the workspace it targets (``targets_workspace``) and
the provider-contract version it satisfies (``contract_version``). The binder only
binds an implementation to a provider when that provider is present and enabled in
the lock AND the implementation's contract_version is SemVer-compatible with the
provider's declared contract_version. A contract drift (e.g. a major-version
mismatch), or a targeted provider that is absent or disabled, is refused BEFORE the
workspace instance is resolved or the implementation is spawned — so a drifted
implementation never silently runs against the wrong runtime.

GREEN targets:
- ``contract_compatible`` implements caret/SemVer compatibility (same major, impl
  range satisfied by the provider's contract_version).
- ``resolve_workspace`` looks up ``implementation['targets_workspace']`` in
  ``providers`` (raising ProviderNotFoundError when absent/disabled) and checks the
  contract (raising ContractMismatchError when incompatible), returning a
  ``WorkspaceBinding``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from atdd.substrate.binding import ContractMismatchError, ProviderNotFoundError


@dataclass
class WorkspaceBinding:
    """A resolved, contract-compatible implementation->provider binding.

    ``realizes_convention`` mirrors the manifest: one convention, or the list a
    family detector realizes from a single run.
    """

    implementation_id: str
    workspace_id: str
    contract_version: str
    realizes_convention: Union[str, list[str]]


def _parse_semver(version: str) -> tuple[int, int, int]:
    parts = str(version).split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ContractMismatchError(f"not a SemVer version: {version!r}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def contract_compatible(impl_contract: str, provider_contract: str) -> bool:
    """Whether an implementation's contract_version is satisfied by the provider's.

    Caret/SemVer semantics: compatible iff the major versions match and the
    provider's (minor, patch) is >= the implementation's required (minor, patch).
    A provider may add backward-compatible capability within the same major; it
    may not satisfy an implementation that needs a newer minor than it offers.
    """
    im, imn, imp = _parse_semver(impl_contract)
    pm, pmn, pmp = _parse_semver(provider_contract)
    if im != pm:
        return False
    return (pmn, pmp) >= (imn, imp)


def resolve_workspace(implementation: dict, providers: dict) -> WorkspaceBinding:
    """Resolve the workspace an implementation targets, refusing on any incompatibility.

    Looks up ``targets_workspace`` in ``providers`` (raising ``ProviderNotFoundError``
    when absent or disabled) and checks the SemVer contract (raising
    ``ContractMismatchError`` when incompatible) BEFORE any workspace instance is
    resolved or the implementation is spawned.
    """
    impl_id = implementation.get("implementation_id", "<unknown>")
    target = implementation.get("targets_workspace")
    provider = providers.get(target)
    if provider is None:
        raise ProviderNotFoundError(
            f"{impl_id}: targeted workspace {target!r} is not present in the lock"
        )
    if not provider.get("enabled", True):
        raise ProviderNotFoundError(
            f"{impl_id}: targeted workspace {target!r} is present but not enabled"
        )

    impl_contract = implementation.get("contract_version", "")
    provider_contract = provider.get("contract_version", "")
    if not contract_compatible(impl_contract, provider_contract):
        raise ContractMismatchError(
            f"{impl_id}: contract_version {impl_contract!r} is not compatible with "
            f"workspace {target!r} contract_version {provider_contract!r}"
        )

    return WorkspaceBinding(
        implementation_id=impl_id,
        workspace_id=target,
        contract_version=impl_contract,
        realizes_convention=implementation.get("realizes_convention", ""),
    )
