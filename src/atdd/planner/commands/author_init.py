# Component: component:author-atdd-substrate:substrate-spine:AuthorInit:backend:application
"""Package scaffolders for ``atdd author {extension,workspace} init`` (P002).

Create a new, self-contained ATDD package boundary — manifest + canonical folder
skeleton — by construction. ``extension init`` scaffolds a use-case extension;
``workspace init`` scaffolds a first-class workspace provider. Both validate the
namespaced package id (reusing the spine's namespace + reserved-publisher guard)
and refuse to overwrite an existing package, so authoring never begins from a
hand-rolled or malformed package shape.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_context import (
    extension_package_home,
    validate_extension_id,
    validate_workspace_id,
    workspace_package_home,
)
from atdd.planner.commands.author_manifest import (
    validate_extension_manifest,
    validate_workspace_manifest,
)

logger = logging.getLogger(__name__)

# Canonical folder skeletons (mirror the templates in the atdd-extensions hub).
_EXTENSION_DIRS = (
    "conventions", "relationships", "validators", "scopes", "gates", "schemas", "e2e",
)
_WORKSPACE_DIRS = ("runtime", "adapter", "conformance", "e2e")


def _name_of(package_id: str) -> str:
    """The artifact-name segment of a ``<publisher>.<scope>.<name>`` id."""
    return package_id.rsplit(".", 1)[-1]


def _scaffold(pkg_dir: Path, subdirs, manifest_name: str, manifest: dict) -> Path:
    """Create the package dir + skeleton + manifest; never overwrite (P002)."""
    if pkg_dir.exists():
        raise AuthorInputError(
            manifest.get("kind", "package"),
            f"package already exists at {pkg_dir} — refusing to overwrite",
        )
    pkg_dir.mkdir(parents=True)
    for sub in subdirs:
        d = pkg_dir / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()
    with (pkg_dir / manifest_name).open("w", encoding="utf-8") as fh:
        yaml.safe_dump(manifest, fh, sort_keys=False, default_flow_style=False)
    return pkg_dir


def init_extension_package(
    extension_id: str,
    *,
    role: str = "coder",
    flow_wagon: str = "validate-source-surface",
    feature: str | None = None,
    root: Path | str = ".",
) -> Path:
    """Scaffold a new extension package; return its root dir.

    Validates the id (``<publisher>.extension.<name>``), then writes
    ``<root>/extensions/<id>/atdd.extension.yaml`` + the canonical skeleton.
    """
    validate_extension_id(extension_id)
    pkg = extension_package_home(extension_id, Path(root))
    manifest = {
        "schema_version": "1.0.0",
        "extension_id": extension_id,
        "version": "0.1.0",
        "kind": "extension",
        "role": role,
        "flow_wagon": flow_wagon,
        "feature": feature or _name_of(extension_id),
        "owns": {
            "conventions": [], "relationships": [], "implementations": [],
            "schemas": [], "gates": [], "scopes": [],
        },
        "depends_on": {"core": [], "workspaces": []},
        "removal_policy": {"allowed_if_no_external_dependents": True},
    }
    validate_extension_manifest(manifest)  # scaffold a valid manifest by construction
    return _scaffold(pkg, _EXTENSION_DIRS, "atdd.extension.yaml", manifest)


def init_workspace_package(
    workspace_id: str,
    *,
    language: str = "python",
    runner: str = "pytest",
    command: str | None = None,
    root: Path | str = ".",
) -> Path:
    """Scaffold a new workspace provider package; return its root dir.

    Validates the id (``<publisher>.workspace.<name>``), then writes
    ``<root>/workspaces/<id>/atdd.workspace.yaml`` (with ``contract_version``) +
    the canonical runtime skeleton.
    """
    validate_workspace_id(workspace_id)
    pkg = workspace_package_home(workspace_id, Path(root))
    manifest = {
        "schema_version": "1.0.0",
        "workspace_id": workspace_id,
        "version": "0.1.0",
        "kind": "workspace",
        "contract_version": "1.0.0",
        "runtime": {
            "language": language,
            "runner": runner,
            "package_manager": "pip",
            "command": command or runner,
        },
        "shared_runtime": {"files": []},
        "discovers": {
            "implementations": ["**/atdd.implementation.yaml"],
            "requires_contract": "^1.0.0",
        },
        "conformance": {"suite": "conformance/"},
        "governed_by_conventions": [],
    }
    validate_workspace_manifest(manifest)  # scaffold a valid manifest by construction
    return _scaffold(pkg, _WORKSPACE_DIRS, "atdd.workspace.yaml", manifest)
