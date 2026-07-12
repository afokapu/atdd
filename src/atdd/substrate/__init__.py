"""ATDD substrate admission layer (wagon: admit-substrate).

The substrate front door: admit external extension/workspace packages into a
project's local substrate — validated, digest-pinned, locked, and NON-EXECUTING.
`pip install atdd` ships only the core engine; `atdd add` admits substrate; core
composes from `.atdd/substrate.lock.yaml`.

Admission inspects manifests, validates against core, composes an in-memory
protocol view, records a sha256 digest, and installs into a versioned `.atdd/`
home. It NEVER imports or executes an extension implementation module — runtime
binding is a strictly later, separately-gated wagon (`bind-substrate-runtime`).
"""
from __future__ import annotations

__all__ = ["schemas", "admission"]
