# Component: component:author-atdd-substrate:substrate-spine:AuthorSpine:backend:application
"""`atdd author` — author schema-valid ATDD substrate artifacts by construction.

Shared spine for the `author-atdd-substrate` wagon. Every per-kind writer
routes through ``validate_author_input`` before any write path runs, so no
invalid role, id, or path ever reaches disk (WMBT C001). The convention-node
writer (E001/C002) is implemented here; relationship/scope/gate writers land
in follow-up slices.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# The four ATDD convention-owning roles. `reviewer` is a spawn persona, not a
# convention role, so it is intentionally excluded.
ROLES: tuple[str, ...] = ("planner", "tester", "coder", "coach")

# Frozen convention-node vocabularies (spec §5.1), consumed not redefined.
KINDS: tuple[str, ...] = (
    "family", "rule", "principle", "constraint",
    "exception", "pattern", "anti_pattern", "policy",
)
STATUSES: tuple[str, ...] = ("draft", "active", "deprecated")

# rule_id: dot-separated lowercase kebab segments, role-prefixed.
_RULE_ID_RE = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$")
# term_id: semantic snake_case; numbered ids (T1/T2/T3) are forbidden (§D005).
_TERM_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_NUMBERED_TERM_RE = re.compile(r"^[Tt]\d+$")
_NODE_REQUIRED = ("schema_version", "rule_id", "kind", "status", "statement", "terms")

_SRC_ROOT = os.path.join("src", "atdd")


class AuthorInputError(Exception):
    """Raised when the spine/writer rejects an author input.

    Carries the offending ``field`` so callers and tests can assert *why*.
    """

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


def validate_author_input(
    role: str, rule_id: str, path: Path, *, home_root: str = _SRC_ROOT
) -> None:
    """Validate role, rule_id and path before any per-kind writer runs.

    Raises ``AuthorInputError`` (with ``.field``) on the first violation:
    role not in :data:`ROLES`; rule_id not lowercase-kebab dot-segments or not
    prefixed by ``role``; path escaping ``home_root``.
    """
    if role not in ROLES:
        raise AuthorInputError(
            "role", f"invalid role {role!r}; expected one of {', '.join(ROLES)}"
        )

    if not _RULE_ID_RE.match(rule_id) or rule_id.split(".", 1)[0] != role:
        raise AuthorInputError(
            "rule_id",
            f"invalid rule_id {rule_id!r}; must be lowercase kebab dot-segments "
            f"prefixed by the role {role!r} (e.g. {role}.green.some-slug)",
        )

    home = os.path.normpath(str(home_root))
    norm = os.path.normpath(str(path))
    if not (norm == home or norm.startswith(home + os.sep)):
        raise AuthorInputError(
            "path", f"path {str(path)!r} escapes the canonical home {home}{os.sep}"
        )


def validate_convention_node(node: dict, path: Path) -> None:
    """Validate a convention-node dict + its target path against the schema (§5).

    Checks: flat path directly under ``nodes/`` (no semantic subfolder);
    required fields present; ``kind``/``status`` in the frozen enums; every
    ``term_id`` semantic snake_case (not numbered). Emits the non-blocking
    §D006 term-count band warning. Raises ``AuthorInputError`` on violation.
    """
    # flat home: core uses .../nodes/, an extension uses .../conventions/ —
    # both flat, no semantic subfolder (nodes/green/) allowed.
    if path.parent.name not in ("nodes", "conventions"):
        raise AuthorInputError(
            "path",
            f"convention nodes must be flat under nodes/ (core) or conventions/ "
            f"(extension), not a subfolder ({path.parent}) — §3.1",
        )

    for field in _NODE_REQUIRED:
        if field not in node or node[field] in (None, "", []):
            raise AuthorInputError(field, f"missing required field {field!r} (§5.2)")

    if node["kind"] not in KINDS:
        raise AuthorInputError("kind", f"invalid kind {node['kind']!r}; one of {KINDS}")
    if node["status"] not in STATUSES:
        raise AuthorInputError("status", f"invalid status {node['status']!r}; one of {STATUSES}")

    for term in node["terms"]:
        tid = term.get("term_id", "")
        if _NUMBERED_TERM_RE.match(tid) or not _TERM_ID_RE.match(tid):
            raise AuthorInputError(
                "terms",
                f"invalid term_id {tid!r}; must be semantic snake_case, not "
                f"numbered (T1/T2/T3 forbidden — §D005)",
            )

    # §D006 term-count heuristic — warn, never block.
    n = len(node["terms"])
    if 8 <= n <= 10:
        print(f"atdd author: warning — {n} terms; review for splitting (§D006)", file=sys.stderr)
    elif n > 10:
        print(
            f"atdd author: warning — {n} terms; likely too large unless justified (§D006)",
            file=sys.stderr,
        )


def _node_path(role: str, rule_id: str, root: Path) -> Path:
    """Canonical flat per-role home for a convention-node file (spec §3.1)."""
    return root / role / "conventions" / "nodes" / f"{rule_id}.convention.yaml"


def create_convention_node(
    role: str,
    rule_id: str,
    *,
    kind: str = "rule",
    status: str = "active",
    name: str | None = None,
    statement: str = "",
    implementation: dict | None = None,
    source: dict | None = None,
    content: dict | None = None,
    metadata: dict | None = None,
    parity: dict | None = None,
    terms: list | None = None,
    root: Path | str | None = None,
    path: Path | str | None = None,
) -> Path:
    """Author one flat schema-valid convention-node (1.1.0); return its path.

    Per-rule_id file => conflict-free with sibling rules. Validates input
    (spine) and node (schema) before writing; never writes a partial artifact.
    When ``path`` is given (e.g. an extension home) it is used verbatim;
    otherwise the core ``<root>/<role>/conventions/nodes/`` home is computed.

    Emits the canonical 1.1.0 field order: identity (schema_version, rule_id,
    kind, status, name), ``statement``, the ``implementation`` enforcement
    binding, ``source`` provenance, the ``content`` body, ``metadata``,
    ``parity`` tracking, then ``terms``. Every optional block is emitted only
    when provided. ``terms`` may carry the optional ``label``/``values``/
    ``examples`` keys per term and are written through verbatim.
    """
    if path is not None:
        path = Path(path)
        home_root = str(path.parent)
    else:
        root = Path(root) if root is not None else Path(_SRC_ROOT)
        path = _node_path(role, rule_id, root)
        home_root = str(root)
    validate_author_input(role, rule_id, path, home_root=home_root)

    node: dict = {
        "schema_version": "1.1.0",
        "rule_id": rule_id,
        "kind": kind,
        "status": status,
    }
    if name:
        node["name"] = name
    node["statement"] = statement
    if implementation:
        node["implementation"] = implementation
    if source:
        node["source"] = source
    if content:
        node["content"] = content
    if metadata:
        node["metadata"] = metadata
    if parity:
        node["parity"] = parity
    node["terms"] = terms or []
    validate_convention_node(node, path)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(node, fh, sort_keys=False, default_flow_style=False)
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd author",
        description="Author schema-valid ATDD substrate artifacts by construction.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    def ctx_flags(p):
        # extension-first: default writes into an extension; --core is explicit.
        p.add_argument("--core", action="store_true",
                       help="author into the ATDD core protocol (explicit; modifies core)")
        p.add_argument("--extension", default=None,
                       help="author into this extension package (default context)")
        p.add_argument("--root", default=None,
                       help="repo root the home is resolved against (default: cwd)")

    cn = sub.add_parser("convention-node", help="author a flat convention node")
    ctx_flags(cn)
    cn.add_argument("--role", default=None, help="core role (required with --core; derived from rule_id in an extension)")
    cn.add_argument("--rule-id", required=True, dest="rule_id", help="canonical rule_id")
    cn.add_argument("--kind", default="rule", help=f"one of {', '.join(KINDS)}")
    cn.add_argument("--status", default="active", help=f"one of {', '.join(STATUSES)}")
    cn.add_argument("--name", default=None, help="human-readable display name")
    cn.add_argument("--statement", default="", help="one-sentence rule statement")
    cn.add_argument("--impl-type", default=None, dest="impl_type",
                    choices=["validator", "manual", "advisory", "none"],
                    help="implementation/enforcement type (1.1.0)")
    cn.add_argument("--impl-ref", default=None, dest="impl_ref",
                    help="implementation ref, e.g. <module>::<test> for type=validator")
    cn.add_argument("--rationale", default=None, help="content.summary — why this convention exists")
    cn.add_argument("--normative", default=None, help="content.normative_text — the full normative body")
    cn.add_argument("--note", dest="notes", default=None, help="content.operational_guidance")
    cn.add_argument("--fix-hint", dest="fix_hint", default=None, help="content.fix_hint — remediation guidance")
    cn.add_argument(
        "--term", action="append", default=[], dest="terms",
        help="a term as 'term_id=text' (repeatable)",
    )
    cn.add_argument(
        "--example-positive", action="append", default=[], dest="examples_positive",
        help="a node-level positive example (§5.1, repeatable)",
    )
    cn.add_argument(
        "--example-negative", action="append", default=[], dest="examples_negative",
        help="a node-level negative example (§5.1, repeatable)",
    )
    cn.add_argument("--legacy-path", default=None, dest="legacy_path",
                    help="source provenance: legacy convention path this node atomises")
    cn.add_argument("--legacy-section", default=None, dest="legacy_section",
                    help="source provenance: legacy section/key this node atomises")
    cn.add_argument("--legacy-rule-id", default=None, dest="legacy_rule_id",
                    help="source provenance: legacy rules[].id this node maps to (if any)")
    cn.add_argument("--extraction-mode", default=None, dest="extraction_mode",
                    choices=["high_fidelity", "summary", "stub"],
                    help="source provenance: extraction fidelity")

    rel = sub.add_parser("relationship", help="author a relationship edge")
    ctx_flags(rel)
    rel.add_argument("--source", required=True, dest="source_ref")
    rel.add_argument("--type", required=True, dest="rel_type")
    rel.add_argument("--target", required=True, dest="target_ref")
    rel.add_argument("--foundation", default=None)
    rel.add_argument("--constraint", default=None)
    rel.add_argument("--control", default=None)
    rel.add_argument("--strength", default=None)
    rel.add_argument("--reason", default="")
    rel.add_argument("--confidence", type=float, default=1.0)
    rel.add_argument("--path", default=None,
                     help="override registry path (default: resolved from context)")

    md = sub.add_parser(
        "merge-driver",
        help="internal: re-sort/dedup git merge driver for registry files",
    )
    md.add_argument("base", help="common ancestor file (git O)")
    md.add_argument("ours", help="current version; merged result is written here (git A)")
    md.add_argument("theirs", help="other version file (git B)")

    sc = sub.add_parser("scope", help="author a scope (validation surface) + an embedded selector")
    ctx_flags(sc)
    sc.add_argument("--scope-id", required=True, dest="scope_id", help="the surface being validated")
    sc.add_argument("--artifact-kind", default=None, dest="artifact_kind")
    sc.add_argument("--runtime", default=None)
    sc.add_argument("--platform", default=None)
    sc.add_argument("--selector-id", required=True, dest="selector_id", help="stable id of the discovery mechanism")
    sc.add_argument("--selector-type", required=True, dest="selector_type",
                    help="path_glob | git_path_prefix | header_scan | manifest_query | github_pr | github_issue | remote_resource | runtime_evidence")
    sc.add_argument("--include", action="append", default=[], help="include pattern (repeatable)")
    sc.add_argument("--exclude", action="append", default=[], help="exclude pattern (repeatable)")
    sc.add_argument("--path", default=None, help="override scope file path (default: resolved from context)")

    gt = sub.add_parser("gate", help="author a gate")
    ctx_flags(gt)
    gt.add_argument("--gate-id", required=True, dest="gate_id")
    gt.add_argument("--trigger-type", required=True, dest="trigger_type")
    gt.add_argument("--trigger-name", required=True, dest="trigger_name")
    gt.add_argument("--selection", required=True, dest="selection_strategy")
    gt.add_argument("--action", required=True, dest="violation_action")
    gt.add_argument("--success-code", type=int, default=0, dest="success_code")
    gt.add_argument("--failure-code", type=int, default=1, dest="failure_code")
    gt.add_argument(
        "--path", default=None,
        help="per-trigger gate file (default: src/atdd/coach/gates/<trigger-name>.yaml)",
    )

    # `extension init` / `workspace init` — scaffold a new package (P002).
    ext = sub.add_parser("extension", help="extension package operations")
    ext_sub = ext.add_subparsers(dest="subcmd", required=True)
    ei = ext_sub.add_parser("init", help="scaffold a new extension package")
    ei.add_argument("--extension", required=True, dest="extension_id",
                    help="<publisher>.extension.<name>")
    ei.add_argument("--role", default="coder", choices=ROLES)
    ei.add_argument("--flow-wagon", default="validate-source-surface", dest="flow_wagon")
    ei.add_argument("--feature", default=None)
    ei.add_argument("--root", default=None, help="repo root (default: cwd)")

    ws = sub.add_parser("workspace", help="workspace provider operations")
    ws_sub = ws.add_subparsers(dest="subcmd", required=True)
    wi = ws_sub.add_parser("init", help="scaffold a new workspace provider package")
    wi.add_argument("--workspace", required=True, dest="workspace_id",
                    help="<publisher>.workspace.<name>")
    wi.add_argument("--language", default="python")
    wi.add_argument("--runner", default="pytest")
    wi.add_argument("--command", default=None, help="run command (default: the runner)")
    wi.add_argument("--root", default=None, help="repo root (default: cwd)")

    return parser


def _parse_terms(raw_terms: list[str]) -> list[dict]:
    out = []
    for raw in raw_terms:
        tid, _, text = raw.partition("=")
        out.append({"term_id": tid.strip(), "text": text.strip()})
    return out


def _config_extensions(root: Path) -> list[str]:
    """Active authoring extensions from .atdd/config.yaml (author.extensions)."""
    cfg = Path(root) / ".atdd" / "config.yaml"
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        return list(((data.get("author") or {}).get("extensions")) or [])
    except Exception as exc:
        logger.debug("no usable author config", extra={"error": str(exc)})
        return []


def run(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    if args.cmd == "merge-driver":
        from atdd.planner.commands.author_registry import merge_registries

        def _read(p: str) -> str:
            try:
                with open(p, encoding="utf-8") as fh:
                    return fh.read()
            except FileNotFoundError:
                logger.debug("merge-driver input absent", extra={"path": p})
                return ""

        merged = merge_registries(_read(args.base), _read(args.ours), _read(args.theirs))
        with open(args.ours, "w", encoding="utf-8") as fh:
            fh.write(merged)
        return 0

    # `init` scaffolds a NEW package boundary, so it needs no authoring context
    # (it creates the package the other kinds then write into) — P002.
    if args.cmd in ("extension", "workspace"):
        from atdd.planner.commands.author_init import (
            init_extension_package, init_workspace_package,
        )

        root = Path(args.root) if getattr(args, "root", None) else Path(os.getcwd())
        try:
            if args.cmd == "extension":
                pkg = init_extension_package(
                    args.extension_id, role=args.role,
                    flow_wagon=args.flow_wagon, feature=args.feature, root=root,
                )
            else:
                pkg = init_workspace_package(
                    args.workspace_id, language=args.language,
                    runner=args.runner, command=args.command, root=root,
                )
        except AuthorInputError as exc:
            logger.warning("atdd author rejected input", extra={"field": getattr(exc, "field", None)})
            print(f"atdd author: {exc}", file=sys.stderr)
            return 2
        print(str(pkg))
        return 0

    # every author kind resolves an authoring context first (P001, spec §6).
    from atdd.planner.commands.author_context import (
        gate_home, node_home, relationship_graph_id, relationship_home,
        resolve_context, scope_home,
    )

    cwd = os.getcwd()
    root = Path(args.root) if getattr(args, "root", None) else Path(cwd)
    try:
        ctx = resolve_context(
            core=args.core, extension=args.extension,
            cwd=cwd, config_extensions=_config_extensions(root),
        )
    except AuthorInputError as exc:
        logger.warning("atdd author rejected input", extra={"field": getattr(exc, "field", None)})
        print(f"atdd author: {exc}", file=sys.stderr)
        return 2

    if args.cmd == "convention-node":
        if ctx.is_core:
            role = args.role
            if not role:
                print("atdd author: --core convention-node requires --role", file=sys.stderr)
                return 2
        else:
            role = args.rule_id.split(".", 1)[0]  # extension: derive role from rule_id
        path = node_home(ctx, role, args.rule_id, root)
        content: dict = {}
        if args.rationale:
            content["summary"] = args.rationale
        if args.normative:
            content["normative_text"] = args.normative
        if args.notes:
            content["operational_guidance"] = args.notes
        if args.examples_positive:
            content["examples"] = list(args.examples_positive)
        if args.examples_negative:
            content["counter_examples"] = list(args.examples_negative)
        if args.fix_hint:
            content["fix_hint"] = args.fix_hint
        implementation: dict = {}
        if args.impl_type:
            implementation["type"] = args.impl_type
        if args.impl_ref:
            implementation.setdefault("type", "validator")
            implementation["ref"] = args.impl_ref
        source: dict = {}
        for key in ("legacy_path", "legacy_section", "legacy_rule_id", "extraction_mode"):
            val = getattr(args, key)
            if val is not None:
                source[key] = val
        try:
            create_convention_node(
                role, args.rule_id, kind=args.kind, status=args.status,
                name=args.name, statement=args.statement,
                implementation=implementation or None, source=source or None,
                content=content or None, terms=_parse_terms(args.terms), path=path,
            )
        except AuthorInputError as exc:
            logger.warning("atdd author rejected input", extra={"field": getattr(exc, "field", None)})
            print(f"atdd author: {exc}", file=sys.stderr)
            return 2
        print(str(path))
        return 0

    if args.cmd == "relationship":
        from atdd.planner.commands.author_registry import insert_relationship

        edge = {
            "source_ref": args.source_ref,
            "type": args.rel_type,
            "target_ref": args.target_ref,
            "reason": args.reason,
            "confidence": args.confidence,
        }
        for key in ("foundation", "constraint", "control", "strength"):
            val = getattr(args, key)
            if val is not None:
                edge[key] = val
        path = Path(args.path) if args.path else relationship_home(ctx, root)
        try:
            insert_relationship(edge, path, graph_id=relationship_graph_id(ctx))
        except AuthorInputError as exc:
            logger.warning("atdd author rejected input", extra={"field": getattr(exc, "field", None)})
            print(f"atdd author: {exc}", file=sys.stderr)
            return 2
        print(str(path))
        return 0

    if args.cmd == "scope":
        from atdd.planner.commands.author_registry import insert_scope_selector

        scope_meta = {"scope_id": args.scope_id}
        for key in ("artifact_kind", "runtime", "platform"):
            val = getattr(args, key)
            if val is not None:
                scope_meta[key] = val
        selector = {"selector_id": args.selector_id, "type": args.selector_type, "include": args.include}
        if args.exclude:
            selector["exclude"] = args.exclude
        path = Path(args.path) if args.path else scope_home(ctx, args.scope_id, root)
        try:
            insert_scope_selector(scope_meta, selector, path)
        except AuthorInputError as exc:
            logger.warning("atdd author rejected input", extra={"field": getattr(exc, "field", None)})
            print(f"atdd author: {exc}", file=sys.stderr)
            return 2
        print(str(path))
        return 0

    if args.cmd == "gate":
        from atdd.planner.commands.author_registry import insert_gate

        path = Path(args.path) if args.path else gate_home(ctx, args.trigger_name, root)
        gate = {
            "gate_id": args.gate_id,
            "kind": "gate",
            "status": "active",
            "trigger": {"type": args.trigger_type, "name": args.trigger_name},
            "selection": {"strategy": args.selection_strategy},
            "on_violation": {"action": args.violation_action},
            "exit": {"success_code": args.success_code, "failure_code": args.failure_code},
        }
        try:
            insert_gate(gate, path)
        except AuthorInputError as exc:
            logger.warning("atdd author rejected input", extra={"field": getattr(exc, "field", None)})
            print(f"atdd author: {exc}", file=sys.stderr)
            return 2
        print(str(path))
        return 0

    return 2
