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
from pathlib import Path

from atdd.planner.commands.author import AuthorInputError

_EXT_DIR = "extensions"


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
    if extension:
        return AuthorContext("extension", extension)
    eid = _extension_from_cwd(Path(cwd or os.getcwd()).resolve())
    if eid:
        return AuthorContext("extension", eid)
    if config_extensions and len(config_extensions) == 1:
        return AuthorContext("extension", config_extensions[0])
    raise AuthorInputError(
        "context",
        "no authoring context: pass --extension <id> (extension-first) or --core "
        "to modify the ATDD protocol (run extension init first if the package "
        "does not exist)",
    )


# --- canonical homes per (kind, context) -------------------------------------
# Core homes match spec §3/§7; extension homes are self-contained per §8.

def node_home(ctx: AuthorContext, role: str, rule_id: str, root: Path) -> Path:
    if ctx.is_core:
        return root / "src" / "atdd" / role / "conventions" / "nodes" / f"{rule_id}.convention.yaml"
    return root / _EXT_DIR / ctx.extension_id / "conventions" / f"{rule_id}.convention.yaml"


def relationship_home(ctx: AuthorContext, root: Path) -> Path:
    if ctx.is_core:
        return root / "src" / "atdd" / "coach" / "graph" / "relationships.yaml"
    return root / _EXT_DIR / ctx.extension_id / "relationships.yaml"


def scope_home(ctx: AuthorContext, root: Path) -> Path:
    if ctx.is_core:
        return root / "src" / "atdd" / "coach" / "selectors" / "scopes.yaml"
    return root / _EXT_DIR / ctx.extension_id / "scopes.yaml"


def gate_home(ctx: AuthorContext, trigger_name: str, root: Path) -> Path:
    if ctx.is_core:
        return root / "src" / "atdd" / "coach" / "gates" / f"{trigger_name}.yaml"
    return root / _EXT_DIR / ctx.extension_id / "gates" / f"{trigger_name}.fragment.yaml"
