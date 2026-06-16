# Component: component:author-atdd-substrate:substrate-spine:AuthorContext:backend:application
"""Authoring context resolution for `atdd author` (P001).

`atdd author` is extension-first: by default it writes into a self-contained
**extension** package; it writes into the ATDD **core** protocol only with an
explicit ``--core`` flag. This module resolves the context (spec §6) and maps a
(kind, context) pair to the canonical home — the *only* thing that differs
between extension and core authoring. The writers, schemas, vocabularies and
merge driver are reused unchanged.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from atdd.planner.commands.author import AuthorInputError

_EXT_DIR = "extensions"
_WS_DIR = "workspaces"

# Package namespace: <publisher>.<scope>.<artifact-name> (all lowercase kebab).
# scope ∈ {core, extension, workspace}: ``core`` is the ATDD protocol, ``extension``
# is a use-case package, ``workspace`` is a first-class reusable runtime provider
# (e.g. ``atdd.workspace.python-pytest``) that many extensions may target.
_PKG_ID_RE = re.compile(
    r"^(?P<publisher>[a-z][a-z0-9-]*)\.(?P<scope>core|extension|workspace)\.(?P<name>[a-z][a-z0-9-]*)$"
)
_RESERVED_PUBLISHER = "atdd"  # only official ATDD packages may use it


def _validate_package_id(
    value: str, *, expected_scope: str, field: str, allow_reserved: bool = False
) -> None:
    """Validate a package id against ``<publisher>.<expected_scope>.<name>``.

    Shared spine for the scoped id classes (extension, workspace). The scope
    segment must equal ``expected_scope``. The reserved-publisher (``atdd``)
    rule is an *authoring* guard — it stops an end user claiming the official
    namespace, but structural validation of an already-official manifest passes
    ``allow_reserved=True`` so an official ``atdd.*`` id is accepted. Raises
    ``AuthorInputError(field=field)``.
    """
    m = _PKG_ID_RE.match(value or "")
    if not m:
        raise AuthorInputError(
            field,
            f"invalid {field} id {value!r}; expected "
            f"<publisher>.{expected_scope}.<artifact-name> (lowercase kebab)",
        )
    if m.group("scope") != expected_scope:
        raise AuthorInputError(
            field,
            f"{field} ids must use the '{expected_scope}' scope "
            f"(got '{m.group('scope')}')",
        )
    if not allow_reserved and m.group("publisher") == _RESERVED_PUBLISHER:
        raise AuthorInputError(
            field,
            f"the '{_RESERVED_PUBLISHER}' publisher is reserved for official ATDD "
            f"packages; use your own publisher namespace",
        )


def validate_extension_id(extension_id: str, *, allow_reserved: bool = False) -> None:
    """Validate an ``--extension`` id against ``<publisher>.extension.<name>``.

    Per the locked package-namespace rule: the second segment must be
    ``extension`` (``--core`` owns ``.core.``), and ``atdd`` is a reserved
    publisher for official packages (``allow_reserved=True`` to accept official
    ids during structural validation). Raises ``AuthorInputError(field="extension")``.
    """
    _validate_package_id(extension_id, expected_scope="extension", field="extension",
                         allow_reserved=allow_reserved)


def validate_workspace_id(workspace_id: str, *, allow_reserved: bool = False) -> None:
    """Validate a workspace-provider id against ``<publisher>.workspace.<name>``.

    Workspace providers are first-class, reusable, domain-agnostic runtimes
    (e.g. ``acme.workspace.python-pytest``) that extensions target by id +
    contract version. Same grammar and reserved-publisher rule as extensions,
    with the ``workspace`` scope. Pass ``allow_reserved=True`` to accept an
    official ``atdd.*`` id. Raises ``AuthorInputError(field="workspace")``.
    """
    _validate_package_id(workspace_id, expected_scope="workspace", field="workspace",
                         allow_reserved=allow_reserved)


class AuthorContext:
    """A resolved authoring context: ``core`` or an ``extension`` (with id)."""

    def __init__(self, mode: str, extension_id: str | None = None) -> None:
        self.mode = mode  # "core" | "extension"
        self.extension_id = extension_id

    @property
    def is_core(self) -> bool:
        return self.mode == "core"

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"AuthorContext({self.mode}, {self.extension_id!r})"


def _extension_from_cwd(cwd: Path) -> str | None:
    """If ``cwd`` is inside ``<repo>/extensions/<id>/…``, return ``<id>``."""
    parts = cwd.parts
    if _EXT_DIR in parts:
        i = parts.index(_EXT_DIR)
        if i + 1 < len(parts):
            return parts[i + 1]
    return None


def resolve_context(
    *,
    core: bool = False,
    extension: str | None = None,
    cwd: str | os.PathLike | None = None,
    config_extensions: list[str] | None = None,
) -> AuthorContext:
    """Resolve the authoring context per spec §6 (in order):

    1. ``--core`` → core context.
    2. ``--extension <id>`` → that extension context.
    3. cwd inside ``extensions/<id>/`` → that extension context.
    4. config declares exactly one active authoring extension → use it.
    5. otherwise fail, asking for ``--extension`` or ``--core``.
    """
    if core:
        return AuthorContext("core")
    eid = extension or _extension_from_cwd(Path(cwd or os.getcwd()).resolve())
    if not eid and config_extensions and len(config_extensions) == 1:
        eid = config_extensions[0]
    if eid:
        validate_extension_id(eid)  # any resolved extension id must be well-formed
        return AuthorContext("extension", eid)
    raise AuthorInputError(
        "context",
        "no authoring context: pass --extension <id> (extension-first) or --core "
        "to modify the ATDD protocol (run extension init first if the package "
        "does not exist)",
    )


# --- canonical homes per (kind, context) -------------------------------------
# Core homes match spec §3/§7; extension homes are self-contained per §8.

def extension_package_home(extension_id: str, root: Path) -> Path:
    """Package-root dir for an extension scaffold: ``<root>/extensions/<id>/``."""
    return root / _EXT_DIR / extension_id


def workspace_package_home(workspace_id: str, root: Path) -> Path:
    """Package-root dir for a workspace provider scaffold: ``<root>/workspaces/<id>/``."""
    return root / _WS_DIR / workspace_id


def node_home(ctx: AuthorContext, role: str, rule_id: str, root: Path) -> Path:
    if ctx.is_core:
        return root / "src" / "atdd" / role / "conventions" / "nodes" / f"{rule_id}.convention.yaml"
    return root / _EXT_DIR / ctx.extension_id / "conventions" / f"{rule_id}.convention.yaml"


def relationship_home(ctx: AuthorContext, root: Path) -> Path:
    if ctx.is_core:
        return root / "src" / "atdd" / "coach" / "graph" / "relationships.yaml"
    return root / _EXT_DIR / ctx.extension_id / "relationships.yaml"


def scope_home(ctx: AuthorContext, scope_id: str, root: Path) -> Path:
    # V1: scope is primary — per-file under scopes/, selectors embedded.
    if ctx.is_core:
        return root / "src" / "atdd" / "coach" / "selectors" / "scopes" / f"{scope_id}.scope.yaml"
    return root / _EXT_DIR / ctx.extension_id / "scopes" / f"{scope_id}.scope.yaml"


def gate_home(ctx: AuthorContext, trigger_name: str, root: Path) -> Path:
    if ctx.is_core:
        return root / "src" / "atdd" / "coach" / "gates" / f"{trigger_name}.yaml"
    return root / _EXT_DIR / ctx.extension_id / "gates" / f"{trigger_name}.fragment.yaml"
