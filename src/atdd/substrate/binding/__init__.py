"""Substrate runtime binder (wagon: bind-substrate-runtime).

The third and final substrate stage (author -> admit -> bind): turn a locked,
inert ``.atdd/substrate.lock.yaml`` into running, gating capabilities. Admission
installs packages but never executes them; this package is the FIRST layer that
runs admitted code, so every executing path is gated behind a digest re-verify
(``lock_loader.verify_package_digest``) and a SemVer contract check
(``resolver.resolve_workspace``). Execution itself is PROVIDER-SPAWN — a
subprocess in the workspace provider's runtime — so core imports no extension
code.

This module exposes the binding error hierarchy; the pipeline stages live in the
sibling modules (``schemas``, ``lock_loader``, ``resolver``, ...).
"""
from __future__ import annotations


class BindingError(Exception):
    """Base class for all substrate-binding failures."""


class DigestMismatchError(BindingError):
    """An installed package's recomputed digest does not match the lock (tamper)."""


class ContractMismatchError(BindingError):
    """An implementation's contract_version is incompatible with its provider."""


class ProviderNotFoundError(BindingError):
    """An implementation targets a workspace provider absent or disabled in the lock."""


__all__ = [
    "BindingError",
    "DigestMismatchError",
    "ContractMismatchError",
    "ProviderNotFoundError",
]
