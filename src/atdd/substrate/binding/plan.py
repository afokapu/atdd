"""Compose the binding plan from the locked substrate (WMBT D001/L001/C002).

``build_binding_plan`` turns a locked, enabled substrate into a ``.atdd/binding.lock.yaml``
structure: for every implementation an enabled package ships, it resolves the
targeted workspace and the SemVer contract — a compatible pairing becomes a
``bound`` convention entry; an incompatible or absent-provider pairing degrades to
``legacy-fallback`` (logged). The plan is keyed to a digest of the substrate lock
so it is reproducible and invalidated when the substrate changes.

This is the ``atdd bind --check`` compose path: it inspects manifests and does
contract math only — it NEVER provider-spawns an implementation (execution happens
at gate time, not plan time).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from atdd.substrate.binding import (
    ContractMismatchError,
    ProviderNotFoundError,
    composer,
    lock_loader,
    resolver,
    schemas,
)

PLAN_FILE = "binding.lock.yaml"
PLAN_SCHEMA_VERSION = "1.0.0"


def substrate_lock_digest(project_root: str | Path) -> str:
    """sha256 of the substrate lock file the plan is keyed to (reproducibility)."""
    lock = Path(project_root) / ".atdd" / "substrate.lock.yaml"
    data = lock.read_bytes() if lock.exists() else b""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _provider_contracts(packages: list[lock_loader.LoadedPackage]) -> dict[str, dict]:
    """Map workspace_id -> {contract_version, enabled} from loaded workspace packages."""
    providers: dict[str, dict] = {}
    for pkg in packages:
        if pkg.kind != "workspace":
            continue
        providers[pkg.id] = {
            "contract_version": str(pkg.manifest.get("contract_version", "")),
            "enabled": True,
        }
    return providers


def build_binding_plan(project_root: str | Path, *, log=None) -> dict:
    """Compose the binding plan from the enabled, digest-verified substrate.

    Returns a schema-valid ``.atdd/binding.lock.yaml`` dict. Never executes an
    implementation; resolution is manifest inspection + contract math only.
    """
    _log = log or (lambda _m: None)
    packages = lock_loader.load_enabled_packages(project_root)
    index = composer.index_by_convention(packages)
    providers = _provider_contracts(packages)

    conventions: list[dict] = []
    for convention_id in sorted(index):
        impl = index[convention_id]
        try:
            binding = resolver.resolve_workspace(impl, providers)
        except (ContractMismatchError, ProviderNotFoundError) as exc:
            _log(f"[bind] convention {convention_id!r} degraded to legacy-fallback: {exc}")
            conventions.append({"convention_id": convention_id, "disposition": "legacy-fallback"})
            continue
        conventions.append(
            {
                "convention_id": convention_id,
                "disposition": "bound",
                "implementation_id": binding.implementation_id,
                "workspace_id": binding.workspace_id,
                "contract_version": binding.contract_version,
            }
        )

    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "substrate_lock_digest": substrate_lock_digest(project_root),
        "conventions": conventions,
    }
    schemas.validate_binding_lock(plan, source=f"{project_root}/.atdd/{PLAN_FILE}")
    return plan


def write_binding_plan(project_root: str | Path, plan: dict) -> Path:
    """Validate then atomically write ``.atdd/binding.lock.yaml``."""
    import yaml

    schemas.validate_binding_lock(plan)
    dest = Path(project_root) / ".atdd" / PLAN_FILE
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
    tmp.replace(dest)
    return dest
