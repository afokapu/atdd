"""CLI handlers for the four admission commands (WMBTs L001/C002/C003/E001/C004).

`atdd search` · `atdd add` · `atdd remove` · `atdd list --substrate`. These are thin
bridges over registry/resolver/admission/installer; they never import or execute
an extension implementation module.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

_log = logging.getLogger(__name__)

from atdd.planner.commands.author_manifest import AuthorInputError
from atdd.planner.commands.compose import CompositionError
from atdd.substrate import admission, installer, registry, resolver
from atdd.substrate.schemas import SubstrateSchemaError

SUBSTRATE_FILE = "substrate.yaml"

# The expected ways admission cleanly REFUSES a package — caught at the CLI
# boundary and reported, not crashed on. Anything else is a real bug and propagates.
_ADMISSION_REFUSALS = (
    admission.AdmissionError,
    AuthorInputError,
    CompositionError,
    SubstrateSchemaError,
)


def _load_registry_entries(project_root: str | Path) -> list[registry.RegistryEntry]:
    """Load entries from every locally-resolvable registry in `.atdd/substrate.yaml`."""
    root = Path(project_root)
    intent_path = root / ".atdd" / SUBSTRATE_FILE
    if not intent_path.exists():
        return []
    intent = yaml.safe_load(intent_path.read_text(encoding="utf-8")) or {}
    entries: list[registry.RegistryEntry] = []
    for reg in intent.get("registries", []):
        index = _registry_index_path(root, reg)
        if index is not None and index.exists():
            entries.extend(registry.load_registry_index(index))
    return entries


def _registry_index_path(root: Path, reg: dict):
    """Locate a registry's index file for locally-resolvable registries (path type)."""
    source = reg.get("source")
    if not source:
        return None
    base = Path(source)
    if not base.is_absolute():
        base = root / base
    return base / reg["path"] if reg.get("path") else base


def run_search(query: str, *, kind: str | None = None, project_root: str | Path = ".") -> int:
    entries = _load_registry_entries(project_root)
    results = registry.search(entries, query, kind=kind)
    if not results:
        print(f"no artifacts match {query!r}")
        return 0
    for e in results:
        print(f"{e.id}  [{e.kind}]  {e.latest_version}  {e.trust or '-'}  aliases={','.join(e.aliases) or '-'}")
    return 0


def run_add(
    *,
    ref: str | None = None,
    path: str | None = None,
    project_root: str | Path = ".",
    dry_run: bool = False,
) -> int:
    if path:
        package_dir = Path(path)
    else:
        entries = _load_registry_entries(project_root)
        try:
            entry = resolver.resolve(ref, entries)
        except resolver.AmbiguousAliasError as exc:
            _log.warning("ambiguous alias refused", extra={"ref": ref, "candidates": exc.candidates})
            print(f"error: {exc}")
            for cid in exc.candidates:
                print(f"  candidate: {cid}")
            return 1
        except resolver.ResolutionError as exc:
            _log.warning("ref did not resolve", extra={"ref": ref, "error": str(exc)})
            print(f"error: {exc}")
            return 1
        package_dir = Path(entry.source)
        if not package_dir.is_absolute():
            package_dir = Path(project_root) / package_dir

    try:
        if dry_run:
            result = admission.validate_and_compose(package_dir)
            print(f"would admit {result.package_id} [{result.kind}] (dry-run; not installed)")
            return 0
        result = admission.admit(package_dir, project_root=project_root)
    except _ADMISSION_REFUSALS as exc:
        _log.warning("admission refused", extra={"package": str(package_dir), "error": str(exc)})
        print(f"error: refused — {exc}")
        return 1
    print(f"admitted {result.package_id} [{result.kind}] -> {result.installed_path}  {result.digest}")
    return 0


def run_remove(
    ref: str, *, project_root: str | Path = ".", force: bool = False, prune: bool = False
) -> int:
    try:
        out = admission.remove(ref, project_root=project_root, force=force, prune=prune)
    except admission.AdmissionError as exc:
        _log.warning("remove refused", extra={"ref": ref, "error": str(exc)})
        print(f"error: {exc}")
        return 1
    msg = f"removed {out['removed']}"
    if out["pruned"]:
        msg += f" (pruned {', '.join(out['pruned'])})"
    print(msg)
    return 0


def run_list(*, project_root: str | Path = ".") -> int:
    arts = installer.list_substrate(project_root)
    if not arts:
        print("substrate is empty (no admitted artifacts)")
        return 0
    for a in arts:
        print(f"{a['id']}  [{a['kind']}]  {a['version']}  {a['digest']}  {a['installed_path']}")
    return 0
