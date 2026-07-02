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


_DETECT_SKELETON = '''#!/usr/bin/env node
// Validator: {impl_id}  — scaffolded by `atdd author implementation init`.
// v1.1 provider contract: read ATDD_SCAN_ROOTS, write RAW
// {{rule_id,file,line,col,evidence,source_line}} violations to
// ATDD_VIOLATIONS_REPORT, exit 0 regardless of count. TODO: implement the checks.
import {{ writeFileSync, readFileSync, statSync, readdirSync }} from "node:fs";
import {{ join, extname, sep }} from "node:path";

const RULE_IDS = {rule_ids_js};
const EXCLUDES = ["_generated", "node_modules", "dist", "build", ".next"];

function parseJsonEnv(name) {{
  try {{ const v = JSON.parse(process.env[name] || "[]"); return Array.isArray(v) ? v : []; }}
  catch {{ return []; }}
}}
function* walk(root) {{
  let st; try {{ st = statSync(root); }} catch {{ return; }}
  if (st.isFile()) {{ yield root; return; }}
  for (const n of readdirSync(root)) {{
    if (EXCLUDES.includes(n)) continue;
    yield* walk(join(root, n));
  }}
}}
function main() {{
  const reportPath = process.env.ATDD_VIOLATIONS_REPORT;
  if (!reportPath) {{ process.stderr.write("validator: ATDD_VIOLATIONS_REPORT not set\\n"); process.exit(2); }}
  const roots = parseJsonEnv("ATDD_SCAN_ROOTS");
  const violations = [];
  for (const root of roots) for (const file of walk(root)) {{
    // TODO: inspect `file` and push {{ rule_id: RULE_IDS[i], file, line, col, evidence, source_line }}.
  }}
  writeFileSync(reportPath, JSON.stringify({{ violations }}, null, 2), "utf8");
  process.exit(0);
}}
main();
'''


def init_implementation_package(
    implementation_id: str,
    *,
    targets_workspace: str,
    emits_rule_ids: list[str],
    root: Path | str = ".",
    dest: str = "implementations",
) -> Path:
    """Scaffold a compliant VALIDATOR implementation by construction (P002 sibling).

    Writes ``<root>/<dest>/<impl>/`` with a manifest that passes
    ``validate_implementation_manifest`` (subtype/entrypoint/report/emits_rule_ids),
    a ``src/detect.mjs`` v1.1 skeleton, and ``tests/`` + ``fixtures/{clean,dirty}/``.
    A FAMILY is authored by passing more than one ``emits_rule_ids``.
    """
    from atdd.planner.commands.author_manifest import validate_implementation_manifest

    if not implementation_id or not str(implementation_id).strip():
        raise AuthorInputError("implementation_id", "implementation_id is required")
    if not emits_rule_ids:
        raise AuthorInputError("emits_rule_ids", "at least one --emits rule_id is required")
    validate_workspace_id(targets_workspace, allow_reserved=True)
    pkg = Path(root) / dest / implementation_id.replace(".", "_")
    if pkg.exists():
        raise AuthorInputError("implementation_id", f"implementation already exists at {pkg} — refusing to overwrite")
    entry = "src/detect.mjs"
    manifest = {
        "schema_version": "1.1.0",
        "kind": "implementation",
        "subtype": "validator",
        "implementation_id": implementation_id,
        "targets_workspace": targets_workspace,
        "contract_version": "1.1.0",
        "realizes_convention": emits_rule_ids[0],
        "emits_rule_ids": list(emits_rule_ids),
        "entrypoint": entry,
        "report": entry,
    }
    validate_implementation_manifest(manifest)  # compliant by construction
    for sub in ("src", "tests", "fixtures/clean", "fixtures/dirty"):
        d = pkg / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()
    rule_ids_js = "[" + ", ".join(f'"{r}"' for r in emits_rule_ids) + "]"
    (pkg / "src" / "detect.mjs").write_text(
        _DETECT_SKELETON.format(impl_id=implementation_id, rule_ids_js=rule_ids_js))
    with (pkg / "atdd.implementation.yaml").open("w", encoding="utf-8") as fh:
        yaml.safe_dump(manifest, fh, sort_keys=False, default_flow_style=False)
    return pkg


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
