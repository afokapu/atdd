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


@dataclass
class WorkspaceBinding:
    """A resolved, contract-compatible implementation->provider binding."""

    implementation_id: str
    workspace_id: str
    contract_version: str
    realizes_convention: str


def contract_compatible(impl_contract: str, provider_contract: str) -> bool:
    """Whether an implementation's contract_version is satisfied by the provider's.

    GREEN target: SemVer compatibility (caret semantics — same major, impl version
    range satisfied by provider_contract).
    """
    raise NotImplementedError("C002: SemVer contract compatibility (GREEN)")


def resolve_workspace(implementation: dict, providers: dict) -> WorkspaceBinding:
    """Resolve the workspace an implementation targets, refusing on any incompatibility.

    GREEN target: providers[implementation['targets_workspace']] (ProviderNotFoundError
    if absent/disabled) -> contract_compatible(impl.contract_version,
    provider.contract_version) (ContractMismatchError if not) -> WorkspaceBinding.
    """
    raise NotImplementedError("C002: resolve workspace + contract check (GREEN)")
