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
import copy
import json
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Optional

import yaml

# Issue-body authoring (#1223). Re-exported here so the public author surface is
# `atdd.planner.commands.author.create_issue_body` / `.validate_issue_body`
# (peers of create_convention_node). The module is planner-side and coach-free
# (planner.theme.commons-coach-boundary, #970).
from atdd.planner.commands.author_issue import (  # noqa: F401
    create_issue_body,
    extract_issue_type,
    issue_type_enum,
    validate_issue_body,
)

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

# Canonical (extensible) subject kinds a convention-node `validation` block may
# control (#1247). The schema keeps `subject_kind` an open string so new kinds
# need no schema change; this tuple documents the known set for tooling.
VALIDATION_SUBJECT_KINDS: tuple[str, ...] = (
    "train", "interlocking", "rendered-diagram", "plan-session", "runtime-boundary",
)

# Forbidden key tokens inside a `validation` block (#1247 boundary rules):
# concrete runtime facts (a one-off train_id, route-selection state, Cargo
# contents, a rendered digest, or TrainResult values) belong in generated
# artifacts, traces, or validator evidence — never in convention metadata.
_FORBIDDEN_VALIDATION_KEY_TOKENS: tuple[str, ...] = (
    "train_id", "route_selection", "cargo", "digest", "train_result",
)

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


def _validate_term_ids(terms) -> None:
    """Every ``term_id`` must be semantic snake_case, never numbered (§D005)."""
    for term in terms:
        tid = term.get("term_id", "")
        if _NUMBERED_TERM_RE.match(tid) or not _TERM_ID_RE.match(tid):
            raise AuthorInputError(
                "terms",
                f"invalid term_id {tid!r}; must be semantic snake_case, not "
                f"numbered (T1/T2/T3 forbidden — §D005)",
            )


def _warn_term_count(n: int) -> None:
    """§D006 term-count heuristic — warn, never block."""
    if 8 <= n <= 10:
        print(f"atdd author: warning — {n} terms; review for splitting (§D006)", file=sys.stderr)
    elif n > 10:
        print(
            f"atdd author: warning — {n} terms; likely too large unless justified (§D006)",
            file=sys.stderr,
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

    _validate_term_ids(node["terms"])

    # Optional `validation` metadata (#1247): when present it must be a JSON
    # object with a registry-resolvable family/template and no runtime state.
    if "validation" in node and node["validation"] is not None:
        validate_validation_metadata(node["validation"])

    _warn_term_count(len(node["terms"]))


def _reject_runtime_state(obj, *, _path: str = "validation") -> None:
    """Reject any key carrying concrete runtime state, anywhere in the block.

    Walks the ``validation`` block recursively; raises ``AuthorInputError`` (field
    ``"validation"``) when a key name matches a forbidden runtime token (#1247).
    """
    if isinstance(obj, list):
        for i, item in enumerate(obj):
            _reject_runtime_state(item, _path=f"{_path}[{i}]")
        return
    if not isinstance(obj, dict):
        return
    for key, value in obj.items():
        norm = str(key).lower().replace("-", "_")
        if any(tok in norm for tok in _FORBIDDEN_VALIDATION_KEY_TOKENS):
            raise AuthorInputError(
                "validation",
                f"validation must not carry concrete runtime state (forbidden "
                f"key {key!r} at {_path}); a concrete train_id, route-selection "
                f"state, Cargo contents, rendered digest, or TrainResult value "
                f"belongs in generated artifacts, traces, or validator evidence "
                f"— not convention metadata (#1247)",
            )
        _reject_runtime_state(value, _path=f"{_path}.{key}")


def validate_validation_metadata(validation) -> None:
    """Validate an optional convention-node ``validation`` block (#1247).

    Enforces the boundary rules: it must be a JSON object; it must not embed
    concrete runtime state; and when ``family`` (and optionally ``template``) is
    given they must resolve against ``validators/conventions/registry.yaml``.
    Raises ``AuthorInputError`` (with ``.field``) on the first violation.
    """
    if not isinstance(validation, dict):
        raise AuthorInputError("validation", "validation must be a JSON object")

    _reject_runtime_state(validation)

    family = validation.get("family")
    template = validation.get("template")
    if family is None:
        return  # family/template are optional; nothing left to resolve

    # Lazy import: author_variant imports AuthorInputError from this module.
    from atdd.planner.commands.author_variant import load_registry

    families = load_registry()
    if family not in families:
        raise AuthorInputError(
            "family",
            f"unknown convention family {family!r}; registered: "
            f"{', '.join(sorted(families))}",
        )
    if template is not None and template not in families[family]:
        raise AuthorInputError(
            "template",
            f"template {template!r} is not registered under family {family!r}; "
            f"templates: {', '.join(families[family]) or '(none)'}",
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
    statement: str = "",
    name: str | None = None,
    rationale: str | None = None,
    notes: str | None = None,
    implementation: dict | None = None,
    source: dict | None = None,
    content: dict | None = None,
    bidirectional: list | None = None,
    metadata: dict | None = None,
    parity: dict | None = None,
    validation: dict | None = None,
    terms: list | None = None,
    root: Path | str | None = None,
    path: Path | str | None = None,
) -> Path:
    """Author one flat schema-valid convention-node file; return its path.

    Per-rule_id file => conflict-free with sibling rules. Validates input
    (spine) and node (schema) before writing; never writes a partial artifact.
    When ``path`` is given (e.g. an extension home) it is used verbatim;
    otherwise the core ``<root>/<role>/conventions/nodes/`` home is computed.
    ``rationale`` and ``notes`` are the spec §5.3 optional-but-recommended
    fields; each is emitted (in spec field order) only when provided.
    """
    if path is not None:
        path = Path(path)
        home_root = str(path.parent)
    else:
        root = Path(root) if root is not None else Path(_SRC_ROOT)
        path = _node_path(role, rule_id, root)
        home_root = str(root)
    validate_author_input(role, rule_id, path, home_root=home_root)

    # Emit in convention-node.schema property order; `terms` is required (always last).
    # Rich fields (implementation/source/content/bidirectional/metadata/parity) are the
    # full current model — emitted when provided so authored nodes are not "behind" the
    # convention-graph engine (implementation.ref is the validator binding it reads).
    node: dict = {
        "schema_version": "1.0.0",
        "rule_id": rule_id,
        "kind": kind,
        "status": status,
    }
    if name:
        node["name"] = name
    node["statement"] = statement
    if rationale:
        node["rationale"] = rationale
    node["terms"] = terms or []          # spec §5.1: rationale -> terms -> notes
    if notes:
        node["notes"] = notes
    if implementation:
        node["implementation"] = implementation
    if source:
        node["source"] = source
    if content:
        node["content"] = content
    if bidirectional:
        node["bidirectional"] = bidirectional
    if metadata:
        node["metadata"] = metadata
    if parity:
        node["parity"] = parity
    if validation:
        node["validation"] = validation
    validate_convention_node(node, path)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(node, fh, sort_keys=False, default_flow_style=False)
    return path


# ---------------------------------------------------------------------------
# Plan-layer authoring (wagon / feature / wmbt / train / acceptance).
#
# Sibling of the convention-substrate writers above: these author the *plan*
# artifacts under plan/<slug>/ keyed by URN/slug/step-code (not role.rule_id).
# They reuse the validate-then-write discipline: validate_plan_author_input
# guards every write path so no malformed input reaches disk (WMBT C001).
# ---------------------------------------------------------------------------

_PLAN_ROOT = "plan"
_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_WMBT_CODE_RE = re.compile(r"^[DLPCEMYRK][0-9]{3}$")
_TRAIN_ID_RE = re.compile(r"^[0-9]{4}-[a-z][a-z0-9-]*$")
# Typed train identity (issue #1421): train:<subject>:<slug>. Matches the
# schema's train_id pattern for the typed form; the legacy NNNN-slug form above
# is still accepted during the migration transition.
_TYPED_TRAIN_ID_RE = re.compile(r"^train:[a-z][a-z0-9-]*:[a-z][a-z0-9-]*$")
_TRAIN_CATEGORIES = ("nominal", "error", "alternate", "exception")
_IL_ID_RE = re.compile(r"^interlocking:[a-z][a-z0-9-]*$")
_PLAN_URN_RE = re.compile(r"^[a-z][a-z0-9-]*:[a-z][a-z0-9-]*(:[A-Za-z0-9-]+)*$")

# Wagon manifest required header fields (consume + wmbt are defaulted by the
# writer, so they are not required *inputs*).
_WAGON_REQUIRED_INPUT = ("wagon", "description", "subject", "context", "action", "goal", "outcome", "produce")
_FEATURE_REQUIRED = ("urn", "wagon", "description", "sizing", "wmbts", "components")
_WMBT_REQUIRED = ("step", "direction", "dimension", "object_of_control", "lens", "statement")


def _slug_to_dir(slug: str) -> str:
    return slug.replace("-", "_")


def validate_plan_author_input(
    slug: str, ref: str, path: Path, *, plan_root: str = _PLAN_ROOT
) -> None:
    """Guard every plan-kind writer: reject a bad slug, URN, or out-of-plan path.

    Raises ``AuthorInputError`` (with ``.field``) on the first violation:
    slug not kebab-case; ref not a plan-artifact URN; path escaping ``plan_root``.
    """
    if not _SLUG_RE.match(slug or ""):
        raise AuthorInputError("slug", f"invalid wagon slug {slug!r}; must be kebab-case")
    if not _PLAN_URN_RE.match(ref or ""):
        raise AuthorInputError("ref", f"invalid artifact ref {ref!r}; must be a colon URN")
    home = os.path.normpath(str(plan_root))
    norm = os.path.normpath(str(path))
    if not (norm == home or norm.startswith(home + os.sep)):
        raise AuthorInputError("path", f"path {str(path)!r} escapes the plan home {home}{os.sep}")


def _json_type_name(value: object) -> str:
    """Name the JSON type of ``value`` the way an operator wrote it."""
    if value is None:
        return "null"
    if isinstance(value, bool):  # bool before int: bool is a subclass of int
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    return type(value).__name__


def validate_author_spec(spec: object) -> None:
    """Guard the author spec: it must be a JSON object (WMBT C008).

    Every per-kind plan writer reads its input with ``spec.get(...)``, so a spec
    that is valid JSON but not an object detonates inside the writer, after the
    Confirm lock. Reject it at the input guard instead.

    Raises ``AuthorInputError`` with ``.field == "spec"`` naming the JSON type
    actually received. Returns ``None`` for any dict, including the empty dict.
    """
    if not isinstance(spec, dict):
        raise AuthorInputError(
            "spec",
            f"author spec must be a JSON object, got {_json_type_name(spec)}",
        )


def _plan_root(root: Path | str | None) -> Path:
    return (Path(root) if root is not None else Path.cwd()) / _PLAN_ROOT


class ArtifactReviewError(Exception):
    """A declared authoring-review rule fired; the artifact was NOT written.

    ``findings`` carries the reported records so the authoring agent can correct its
    prose and re-run the same command — that agent-command round trip IS the
    correction loop, which is why core needs no LLM of its own.
    """

    def __init__(self, artifact_kind: str, findings: list) -> None:
        super().__init__(
            f"{artifact_kind}: {len(findings)} authoring-review finding(s); refusing to write"
        )
        self.artifact_kind = artifact_kind
        self.findings = list(findings)


def _repo_root_for(path: Path) -> Optional[Path]:
    """Nearest ancestor of ``path`` holding an ``.atdd/`` directory, if any."""
    for candidate in [path, *path.parents]:
        if (candidate / ".atdd").is_dir():
            return candidate
    return None


def _declared_review_rules(path: Path) -> list:
    """Rule ids the REPO declares as pre-write authoring gates.

    Core names no rule, no checker and no vocabulary of its own — it only reads what
    the repo opted into under ``author_review.rules``. A repo that declares none gets
    the unguarded write path unchanged, which is what keeps an install with no review
    extension free of any controlled-language dependency.

    A malformed config is NOT swallowed: silently returning ``[]`` would disable the
    gate on a typo, and a gate that disables itself quietly is worse than no gate.
    """
    root = _repo_root_for(path)
    if root is None:
        return []
    cfg = root / ".atdd" / "config.yaml"
    if not cfg.is_file():
        return []
    data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    block = data.get("author_review") if isinstance(data, dict) else None
    rules = (block or {}).get("rules") if isinstance(block, dict) else None
    return [r for r in (rules or []) if isinstance(r, str) and r.strip()]


def review_authored_document(artifact_kind: str, doc: dict, *, repo_root: Path, rules: list) -> list:
    """Enforce the declared review ``rules`` over a STAGED copy of ``doc``.

    The staged copy lives in a temp directory outside the repo, so a refused write
    leaves nothing behind at the canonical path. Returns the findings; empty means the
    write may proceed.
    """
    from atdd.enforce.runner import enforce  # local: avoids an import cycle at module load

    with tempfile.TemporaryDirectory(prefix="atdd-author-review-") as staging:
        staged = Path(staging) / f"{artifact_kind}.yaml"
        with staged.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(doc, fh, sort_keys=False, default_flow_style=False)
        result = enforce(Path(repo_root), path_override=[str(staging)], rules=set(rules))

    return [
        {"rule_id": v.rule_id, "locations": list(v.locations), "detail": v.detail}
        for v in result.verdicts
        if v.failed
    ]


def _write_yaml(path: Path, doc: dict, *, artifact_kind: str | None = None) -> Path:
    """Write ``doc`` to ``path``, gated by the repo's declared authoring review.

    ``artifact_kind`` opts this write into the gate. With no kind, or with no rules
    declared, this is the original unguarded write — byte-for-byte.
    """
    if artifact_kind:
        rules = _declared_review_rules(path)
        if rules:  # nothing declared -> the review path is never even consulted
            root = _repo_root_for(path)
            findings = review_authored_document(
                artifact_kind, doc, repo_root=root, rules=rules
            )
            if findings:
                raise ArtifactReviewError(artifact_kind, findings)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(doc, fh, sort_keys=False, default_flow_style=False)
    return path


def _require_fields(doc: dict, fields, label: str) -> None:
    """Raise AuthorInputError(.field) for the first missing/empty required field."""
    for field in fields:
        if field not in doc or doc[field] in (None, "", []):
            raise AuthorInputError(field, f"{label} missing required field {field!r}")


def validate_wagon(manifest: dict) -> None:
    """Reject a structurally invalid wagon manifest before any write (WMBT C002)."""
    _require_fields(manifest, _WAGON_REQUIRED_INPUT, "wagon manifest")
    for entry in manifest.get("produce", []):
        if "name" not in entry or "contract" not in entry or "telemetry" not in entry:
            raise AuthorInputError("produce", "produce entry must carry name/contract/telemetry")


def create_wagon(spec: dict, *, root: Path | str | None = None) -> Path:
    """Author a wagon manifest at plan/<slug>/_<slug>.yaml by construction (WMBT E001)."""
    slug = spec.get("wagon", "")
    plan = _plan_root(root)
    dirname = _slug_to_dir(slug) if _SLUG_RE.match(slug or "") else slug
    path = plan / dirname / f"_{dirname}.yaml"
    validate_plan_author_input(slug, f"wagon:{slug}", path, plan_root=str(plan))

    manifest: dict = {k: spec[k] for k in spec if k not in ("produce", "consume", "wmbt")}
    manifest["produce"] = [
        {"name": e.get("name"), "contract": e.get("contract"),
         "telemetry": e.get("telemetry"), "to": e.get("to", "external")}
        for e in spec.get("produce", [])
    ]
    manifest["consume"] = spec.get("consume", [])
    manifest["wmbt"] = spec.get("wmbt", {"total": 0})
    validate_wagon(manifest)
    return _write_yaml(path, manifest, artifact_kind="wagon")


def validate_feature(feature: dict) -> None:
    """Reject a structurally invalid feature before any write (WMBT C003)."""
    _require_fields(feature, _FEATURE_REQUIRED, "feature")


def create_feature(spec: dict, *, root: Path | str | None = None) -> Path:
    """Author a feature at plan/<slug>/features/<name>.yaml by construction (WMBT E002)."""
    urn = spec.get("urn", "")
    parts = urn.split(":")
    if len(parts) != 3 or parts[0] != "feature":
        raise AuthorInputError("urn", f"invalid feature urn {urn!r}; expected feature:<wagon>:<name>")
    wagon_slug, name = parts[1], parts[2]
    plan = _plan_root(root)
    path = plan / _slug_to_dir(wagon_slug) / "features" / f"{_slug_to_dir(name)}.yaml"
    validate_plan_author_input(wagon_slug, urn, path, plan_root=str(plan))
    validate_feature(spec)
    return _write_yaml(path, dict(spec), artifact_kind="feature")


def _seed_smoke_acceptance(wagon_slug: str, code: str) -> dict:
    return {
        "identity": {
            "urn": f"acc:{wagon_slug}:{code}-SMOKE-001-seed",
            "id": "AC-SMOKE-001",
            "purpose": f"Verify the {code} behaviour against the real CLI in a checkout",
            "phase": "SMOKE",
        },
        "harness": {"type": "integration", "category": "backend"},
        "given": {"abstract": ["a real repo checkout and the installed atdd CLI"]},
        "when": {"abstract": "the behaviour is exercised end-to-end"},
        "then": {"abstract": ["the observable outcome holds"]},
    }


def validate_wmbt(wmbt: dict) -> None:
    """Reject a structurally invalid WMBT before any write (WMBT C004)."""
    for field in _WMBT_REQUIRED:
        if field not in wmbt or wmbt[field] in (None, "", []):
            raise AuthorInputError(field, f"wmbt missing required field {field!r}")
    if wmbt["object_of_control"] not in wmbt.get("statement", ""):
        raise AuthorInputError(
            "statement",
            f"statement must contain its object_of_control {wmbt['object_of_control']!r}",
        )


def create_wmbt(spec: dict, *, root: Path | str | None = None) -> Path:
    """Author a WMBT at plan/<slug>/<CODE>.yaml in ODI grammar, seeding a SMOKE acc (WMBT E003)."""
    wagon_slug = spec.get("wagon_slug", "")
    code = spec.get("code", "")
    if not _WMBT_CODE_RE.match(code or ""):
        raise AuthorInputError("code", f"invalid wmbt code {code!r}; expected e.g. E001")
    plan = _plan_root(root)
    path = plan / _slug_to_dir(wagon_slug) / f"{code}.yaml"
    validate_plan_author_input(wagon_slug, f"wmbt:{wagon_slug}:{code}", path, plan_root=str(plan))

    wmbt: dict = {"urn": f"wmbt:{wagon_slug}:{code}"}
    for k in ("step", "direction", "dimension", "object_of_control", "context_clarifier", "lens", "statement"):
        if k in spec:
            wmbt[k] = spec[k]
    validate_wmbt(wmbt)
    wmbt["acceptances"] = list(spec.get("acceptances") or []) or [_seed_smoke_acceptance(wagon_slug, code)]
    return _write_yaml(path, wmbt, artifact_kind="wmbt")


def validate_train(spec: dict) -> None:
    """Reject a structurally invalid train before any write (WMBT C005).

    Accepts the typed ``train:<subject>:<slug>`` identity (issue #1421) and, for
    the migration transition, the legacy ``NNNN-slug`` form.
    """
    tid = spec.get("train_id", "")
    if not (_TYPED_TRAIN_ID_RE.match(tid or "") or _TRAIN_ID_RE.match(tid or "")):
        raise AuthorInputError(
            "train_id",
            f"invalid train_id {tid!r}; expected typed train:<subject>:<slug> "
            f"or legacy NNNN-kebab-slug",
        )
    category = spec.get("category")
    if category is not None and category not in _TRAIN_CATEGORIES:
        raise AuthorInputError(
            "category",
            f"invalid category {category!r}; expected one of {_TRAIN_CATEGORIES}",
        )


def is_typed_train_id(tid: str) -> bool:
    """True when ``tid`` is a #1421 typed train identity (``train:<subject>:<slug>``)."""
    return bool(_TYPED_TRAIN_ID_RE.match(tid or ""))


def train_bucket(tid: str, spec: dict | None = None) -> tuple[str, str]:
    """The ``(group, sub)`` registry bucket a train entry nests under in _trains.yaml.

    THE single bucket derivation (issue #1504). Both writers of plan/_trains.yaml
    — ``create_train`` here and ``RegistryBuilder.build_trains`` in coach — must
    call this, or the same train_id lands in two buckets and the bucket-local
    dedup in ``_upsert_train_registry`` cannot see the twin.

    Typed ids bucket by subject/category, which is #1421's grammar: identity names
    the journey and category rides as a validated FIELD (train.convention.yaml
    naming.train_id, registry "trains bucketed by subject"). The legacy NNNN-slug
    form keeps its digit buckets during the transition.
    """
    if is_typed_train_id(tid):
        subject = tid[len("train:"):].split(":", 1)[0]
        category = (spec or {}).get("category") or "nominal"
        return subject, category
    return f"{tid[0]}-trains", f"{tid[0]}0-nominal"


def train_relpath(tid: str) -> str:
    """The repo-relative per-train manifest path for a train id.

    Typed ids nest at plan/_trains/<subject>/<slug>.yaml — the legacy flat
    ``plan/_trains/{tid}.yaml`` derivation would name the file after a colon-bearing
    id, which is not a usable filename. Shared with coach for the same reason
    ``train_bucket`` is (#1504).
    """
    if is_typed_train_id(tid):
        subject, slug = tid[len("train:"):].split(":", 1)
        return f"plan/_trains/{subject}/{slug}.yaml"
    return f"plan/_trains/{tid}.yaml"


def _train_home(tid: str, spec: dict, plan: Path) -> tuple:
    """The registry bucket + on-disk home for a train id, as
    ``(group, sub, rel_path, per_train)``.

    Thin composition over the shared ``train_bucket`` / ``train_relpath``
    derivations so the planner and coach writers cannot drift apart (#1504).
    """
    group, sub = train_bucket(tid, spec)
    rel_path = train_relpath(tid)
    return group, sub, rel_path, plan / Path(rel_path).relative_to("plan")


def _reject_legacy_registry_shape(registry_path: Path, registry: object) -> None:
    """Fail loudly on a pre-#1421 ``plan/_trains.yaml`` instead of crashing on it.

    The canonical registry nests theme -> bucket -> entries. Repos initialised by
    an older atdd carry ``trains:`` as a flat LIST, which the nested writes below
    hit as a bare ``AttributeError: 'list' object has no attribute 'setdefault'``
    (issue #1236). The list shape was retired by #1421's typed-URN grammar, so
    this is a migration prompt, not a shape to support: ``atdd registry update
    trains`` already rebuilds a list-shaped registry into the nested form.
    """
    if not isinstance(registry, dict):
        raise AuthorInputError(
            "registry",
            f"{registry_path} is not a mapping (found {type(registry).__name__}); "
            f"expected a 'trains:' mapping. Rebuild it with: atdd registry update trains",
        )
    trains = registry.get("trains")
    if trains is not None and not isinstance(trains, dict):
        raise AuthorInputError(
            "registry",
            f"{registry_path} uses the legacy list-shaped 'trains:' registry "
            f"(retired by #1421's typed train URNs); expected theme -> bucket -> "
            f"entries. Migrate it with: atdd registry update trains",
        )


def _upsert_train_registry(registry_path: Path, tid: str, spec: dict, home: tuple) -> None:
    """Dedup-insert the train's entry into its bucket in plan/_trains.yaml."""
    group, sub, rel_path, _per_train = home
    registry = {}
    if registry_path.exists():
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    _reject_legacy_registry_shape(registry_path, registry)
    registry.setdefault("trains", {})
    bucket = registry["trains"].setdefault(group, {}).setdefault(sub, [])
    if not any(isinstance(e, dict) and e.get("train_id") == tid for e in bucket):
        entry = {
            "train_id": tid,
            "description": spec.get("description", ""),
            "path": rel_path,
            "wagons": spec.get("wagons", []),
        }
        if _TYPED_TRAIN_ID_RE.match(tid):
            entry["category"] = spec.get("category", "nominal")
        bucket.append(entry)
        bucket.sort(key=lambda e: e.get("train_id", ""))
    _write_yaml(registry_path, registry)


def _build_train_doc(tid: str, spec: dict) -> dict:
    """The per-train document written to plan/_trains/<...>.yaml."""
    train_doc: dict = {
        "train_id": tid,
        "title": spec.get("title", tid),
        "description": spec.get("description", ""),
    }
    # `themes` and `sequence` are schema-REQUIRED; `family`, `primary_wagon`,
    # `dependencies` and `acceptances` are optional. All six are copied verbatim
    # and only when supplied — inventing a default would write a schema-invalid
    # value (`themes: []` fails minItems, `family: ""` fails the enum). `wagons`
    # is deliberately absent: train.schema sets additionalProperties=false and
    # defines no such property; it belongs to the _trains.yaml registry entry,
    # and expresses itself here as the `participants` fallback (#1401).
    for key in ("category", "themes", "family", "primary_wagon", "dependencies",
                "sequence", "acceptances"):
        if key in spec:
            train_doc[key] = spec[key]

    # Preserve caller-supplied participants verbatim: train.schema admits
    # wagon:/user:/system: principals, so deriving from `wagons` unconditionally
    # would silently discard every non-wagon participant. Derive only as a
    # fallback, which is what every pre-#1401 caller relied on.
    participants = spec.get("participants")
    if not participants:
        participants = [f"wagon:{w}" for w in spec.get("wagons", [])]
    train_doc["participants"] = list(participants)
    train_doc["status"] = "planned"

    # Adjacent seam (#1265): carry the optional #1248 interlocking back-ref so a
    # train authored as a route's target self-describes its owning interlocking.
    # Pure traceability — it never alters train linearity (train.schema
    # `source_interlocking`). The Confirm gate (#1249) reads the same shape off
    # the kept unit's spec to bind the interlocking it must validate.
    src_il = spec.get("source_interlocking")
    if isinstance(src_il, dict) and src_il.get("interlocking_id") and src_il.get("route_id"):
        train_doc["source_interlocking"] = {
            "interlocking_id": src_il["interlocking_id"],
            "route_id": src_il["route_id"],
        }
    return train_doc


def create_train(spec: dict, *, root: Path | str | None = None) -> Path:
    """Author a train: dedup-insert into _trains.yaml + write plan/_trains/<id>.yaml (WMBT E004)."""
    validate_train(spec)
    tid = spec["train_id"]
    plan = _plan_root(root)
    registry_path = plan / "_trains.yaml"

    # Bucket + on-disk home derivation. Typed ids (issue #1421) nest under
    # plan/_trains/<subject>/<slug>.yaml and bucket by subject/category — the
    # legacy `{tid[0]}-trains` derivation would place a `train:...` id under a
    # nonsense `t-trains` bucket at a colon-named file. The legacy NNNN-slug
    # form keeps its flat home + digit buckets during the transition.
    home = _train_home(tid, spec, plan)
    per_train = home[3]
    _upsert_train_registry(registry_path, tid, spec, home)

    per_train.parent.mkdir(parents=True, exist_ok=True)
    if not per_train.exists():
        _write_yaml(per_train, _build_train_doc(tid, spec))
    return per_train


# Contract identity: theme-first colon hierarchy + optional single dot-variant on
# the aspect — {theme}(:{category})*:{aspect}(.{variant})? in kebab-case
# (artifact-naming.convention v2.1). At least two colon-segments are required
# (a contract needs a theme AND an aspect). #1329 (A) formalizes this into a
# confirm-blocking naming validator this writer will call once it lands; until
# then the shape + theme check below stand in for the prose convention.
_CONTRACT_IDENTITY_RE = re.compile(
    r"^[a-z][a-z0-9-]*(?::[a-z][a-z0-9-]*)+(?:\.[a-z][a-z0-9-]*)?$"
)

_CONTRACTS_ROOT = "contracts"


def _contracts_root(root: Path | str | None) -> Path:
    return (Path(root) if root is not None else Path.cwd()) / _CONTRACTS_ROOT


def _write_json(path: Path, doc: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, indent=2, ensure_ascii=False))
        fh.write("\n")
    return path


def _canonical_theme_set(root: Path | str | None) -> set[str]:
    """The effective theme names for this repo (consumer-aware, #291/#1317).

    Resolves ``get_theme_map(load_atdd_config(root))`` values. Imports from
    ``atdd.coach.utils`` — shared utils, not coach runtime, so the planner
    ``coach-free`` boundary (#970) holds (the theme validators import the same
    way). Degrades to the built-in default names if config load fails.
    """
    from atdd.coach.utils.theme_map import get_theme_map

    base = Path(root) if root is not None else Path.cwd()
    try:
        from atdd.coach.utils.config import load_atdd_config

        config = load_atdd_config(base)
    except Exception as exc:
        logger.debug(
            "contract theme config load failed; using defaults",
            extra={"error": str(exc)},
        )
        config = {}
    return set(get_theme_map(config).values())


def validate_contract(spec: dict, *, root: Path | str | None = None) -> None:
    """Reject a structurally invalid contract before any write (WMBT E008).

    Guards the theme-first identity shape and that its theme resolves via
    ``get_theme_map`` (consumer-repo-aware), plus a required title. Raises
    ``AuthorInputError`` (with ``.field``) on the first violation so the plan
    Confirm gate and the CLI report *why*. Path derivation happens only after
    this passes, so a bad identity never reaches disk.
    """
    identity = (spec.get("identity") or "").strip()
    if not _CONTRACT_IDENTITY_RE.match(identity):
        raise AuthorInputError(
            "identity",
            f"invalid contract identity {identity!r}; expected "
            "{theme}(:{category})*:{aspect}(.{variant})? in kebab-case",
        )
    theme = identity.split(":", 1)[0]
    themes = _canonical_theme_set(root)
    if theme not in themes:
        raise AuthorInputError(
            "theme",
            f"unknown contract theme {theme!r}; must be one of {sorted(themes)} "
            "(artifact-naming.convention; #1329 formalizes)",
        )
    if not (spec.get("title") or "").strip():
        raise AuthorInputError("title", "contract spec missing required field 'title'")


def _contract_paths(identity: str, root: Path | str | None) -> tuple[Path, str]:
    """Derive the (absolute schema path, repo-relative path) from the identity.

    ``{theme}(:{category})*:{aspect}(.{variant})?`` →
    ``contracts/{theme}/…/{aspect}(.{variant}).schema.json`` — every colon
    segment except the last is a directory; the last (aspect + optional
    ``.variant``) is the file stem. Segments are kebab-validated by
    ``validate_contract`` so none can escape the contracts home.
    """
    segments = identity.split(":")
    *dir_segments, leaf = segments
    filename = f"{leaf}.schema.json"
    schema_path = _contracts_root(root).joinpath(*dir_segments, filename)
    rel_path = "/".join([_CONTRACTS_ROOT, *dir_segments, filename])
    return schema_path, rel_path


def _contract_producers(spec: dict) -> list:
    """Normalize producers to a list: prefer ``producers`` (list), else wrap a
    singular ``producer``, else empty. Lets a spec carry either spelling."""
    if spec.get("producers"):
        return list(spec["producers"])
    if spec.get("producer"):
        return [spec["producer"]]
    return []


def _insert_contract_registry(
    registry_path: Path, identity: str, rel_path: str, spec: dict
) -> None:
    """Dedup-insert (or update) the contract's thin registry entry into
    contracts/_contracts.yaml, sorted by identity.

    Shape matches the #1332 (D) coherence validator's contract: a list of
    ``{identity, path, theme, producers, consumers, external?}`` — ``identity``
    is the bare theme-first name (no ``contract:`` prefix; D strips that prefix
    when matching), ``theme`` is its first segment, ``producers``/``consumers``
    are wagon-ref lists. Registry *maintenance* only — the coherence *validator*
    is #1332 / D, which can later ratchet advisory→strict against this shape."""
    registry: dict = {}
    if registry_path.exists():
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    entries = registry.setdefault("contracts", [])
    entry: dict = {
        "identity": identity,
        "path": rel_path,
        "theme": identity.split(":", 1)[0],
        "producers": _contract_producers(spec),
        "consumers": list(spec.get("consumers") or []),
    }
    if spec.get("external"):
        entry["external"] = True
    existing = next(
        (e for e in entries if isinstance(e, dict) and e.get("identity") == identity),
        None,
    )
    if existing is None:
        entries.append(entry)
    else:
        existing.clear()
        existing.update(entry)
    entries.sort(key=lambda e: e.get("identity", "") if isinstance(e, dict) else "")
    _write_yaml(registry_path, registry)


def create_contract(spec: dict, *, root: Path | str | None = None) -> Path:
    """Author a contract as a first-class plan unit: validate-then-write (E008).

    Mirrors :func:`create_train` — validate the spec, derive the file path from
    the theme-first identity (``contracts/{theme}/…/{aspect}.schema.json``),
    write a schema-valid draft-07 JSON Schema whose ``$id`` is
    ``contract:{identity}``, and dedup-insert a thin entry into
    ``contracts/_contracts.yaml``. An invalid identity (bad shape or unknown
    theme) is rejected before any file is written. This is the keystone the
    ``contract`` unit kind dispatches to (build_author_fn + ``atdd author
    contract``), so contracts flow add → decide → confirm → author like every
    other artifact instead of being hand-authored as loose files (#1314 B).
    """
    validate_contract(spec, root=root)
    identity = spec["identity"].strip()
    schema_path, rel_path = _contract_paths(identity, root)

    doc: dict = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": f"contract:{identity}",
        "title": spec["title"],
        "description": spec.get("description", ""),
        "version": spec.get("version", "1.0.0"),
        "type": spec.get("type", "object"),
    }
    for optional in ("properties", "required", "additionalProperties", "$defs"):
        if optional in spec:
            doc[optional] = spec[optional]
    # Carry the producer/consumer provenance the #1332 (D) coherence pass reads,
    # in the same {producers, consumers, external?} shape as the _contracts.yaml
    # registry entry so the schema file and the registry never disagree.
    producers = _contract_producers(spec)
    consumers = list(spec.get("consumers") or [])
    if producers or consumers or spec.get("external"):
        meta: dict = {"producers": producers, "consumers": consumers}
        if spec.get("external"):
            meta["external"] = True
        doc["x-artifact-metadata"] = meta

    _write_json(schema_path, doc)
    _insert_contract_registry(
        _contracts_root(root) / "_contracts.yaml", identity, rel_path, spec
    )
    return schema_path


def validate_interlocking_spec(spec: dict) -> None:
    """Reject a structurally invalid interlocking spec before any write (WMBT E007)."""
    iid = spec.get("interlocking_id", "")
    if not _IL_ID_RE.match(iid or ""):
        raise AuthorInputError(
            "interlocking_id",
            f"invalid interlocking_id {iid!r}; expected interlocking:<kebab-slug>",
        )
    for field in ("schema_version", "title", "theme", "status",
                  "entrypoint", "route_resolution", "lifelines", "routes"):
        if field not in spec or spec[field] in (None, "", []):
            raise AuthorInputError(field, f"interlocking spec missing required field {field!r}")


# Canonical interlocking field order (mirrors train-interlocking.schema.json top
# level). `_write_yaml` uses sort_keys=False, so byte-determinism of the authored
# artifact depends on constructing the dict in exactly this order.
_IL_FIELD_ORDER: tuple[str, ...] = (
    "schema_version", "interlocking_id", "title", "theme", "status",
    "source", "entrypoint", "route_resolution", "lifelines", "messages",
    "fragments", "invariants", "residuals", "routes",
    # #1554: the author's typed per-category not-applicable. Carried through
    # VERBATIM like the rest of the control body — the command must never
    # synthesize an assessment, because auto-emitting a not-applicable basis for
    # every unrouted category is precisely the erosion the closed vocabulary
    # exists to prevent. Omitting the field here would silently drop the author's
    # assessment and make a compliant interlocking unauthorable through the CLI.
    "category_assessment",
)


def _insert_interlocking_registry(
    registry_path: Path, iid: str, rel_path: str, theme, status
) -> None:
    """Dedup-insert (or update) the interlocking's thin registry entry, sorted by
    interlocking_id (shape per train-interlocking-registry.schema.json)."""
    registry: dict = {}
    if registry_path.exists():
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    registry.setdefault("version", "1.0")
    entries = registry.setdefault("interlockings", [])
    entry: dict = {"interlocking_id": iid, "path": rel_path}
    if theme:
        entry["theme"] = theme
    if status in ("draft", "checked", "stale"):
        entry["status"] = status
    existing = next(
        (e for e in entries if isinstance(e, dict) and e.get("interlocking_id") == iid),
        None,
    )
    if existing is None:
        entries.append(entry)
    else:
        existing.update(entry)
    entries.sort(key=lambda e: e.get("interlocking_id", "") if isinstance(e, dict) else "")
    _write_yaml(registry_path, registry)


def create_interlocking(spec: dict, *, root: Path | str | None = None) -> Path:
    """Author an interlocking: stamp derived digests + write the schema-valid
    artifact under the canonical home + dedup-insert its registry entry (WMBT E007).

    The control body (guards/entrypoint/routes/strategy/messages/fragments/
    invariants/residuals) is human-authored input carried through verbatim; the
    command derives ONLY ``source.content_digest`` and each route's
    ``expected_sequence_digest`` via the single-source-of-truth stamp primitive.
    Precondition: every ``route.train_path`` train YAML already exists on disk —
    a missing train raises ``InterlockingError`` before any file is written."""
    from atdd.planner.interlocking import stamp_interlocking_digests

    validate_interlocking_spec(spec)
    iid = spec["interlocking_id"]
    slug = iid.split(":", 1)[-1]
    plan = _plan_root(root)
    repo_root = plan.parent
    rel_path = f"plan/_trains/_interlockings/{slug}.yaml"
    il_path = plan / "_trains" / "_interlockings" / f"{slug}.yaml"
    registry_path = plan / "_trains" / "_interlockings.yaml"
    validate_plan_author_input(slug, iid, il_path, plan_root=str(plan))

    # Build the document in the pinned field order. source.content_digest + each
    # route's expected_sequence_digest are placeholders here; stamp derives them.
    doc: dict = {}
    for fld in _IL_FIELD_ORDER:
        if fld == "source":
            doc["source"] = {"path": rel_path, "content_digest": "PENDING"}
        elif fld in spec:
            doc[fld] = copy.deepcopy(spec[fld])
    for route in doc.get("routes", []):
        if isinstance(route, dict):
            route.setdefault("projection", {}).setdefault("expected_sequence_digest", "PENDING")

    # Stamp BEFORE any write — a missing route train raises here, leaving no file.
    stamped = stamp_interlocking_digests(doc, repo_root)

    _write_yaml(il_path, stamped)
    _insert_interlocking_registry(
        registry_path, iid, rel_path, spec.get("theme"), spec.get("status")
    )
    return il_path


_SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"


def _validate_embedded_acceptance(block: dict) -> None:
    """Reject an acceptance block that acceptance.schema.json would not accept.

    Validates against ``definitions/embedded_acceptance`` — NOT the strict root
    object (#1194). The root shape requires ``signal`` + ``metadata`` and a full
    ``when.action`` / ``then.assertions``; read literally it rejects every real
    WMBT acceptance in ``plan/`` and everything this writer has ever produced,
    which is exactly why #1193 excluded ``acceptance`` from author-time schema
    validation instead of reconciling it. ``embedded_acceptance`` is the shape
    real files carry (1280 of 1334 in-repo acceptances satisfy it today), so it
    is the shape the writer is held to — authored blocks now validate by
    construction rather than by convention.
    """
    import jsonschema

    schema = json.loads(
        (_SCHEMAS_DIR / "acceptance.schema.json").read_text(encoding="utf-8")
    )
    validator = jsonschema.Draft7Validator(
        {**schema, "$ref": "#/definitions/embedded_acceptance"}
    )
    errors = sorted(validator.iter_errors(block), key=str)
    if errors:
        detail = "; ".join(
            f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in errors
        )
        raise AuthorInputError("acceptance", f"acceptance block is not schema-valid: {detail}")


def create_acceptance(wmbt_urn: str, block: dict, *, root: Path | str | None = None) -> Path:
    """Append an acceptance into an existing WMBT's acceptances[], idempotent on urn (WMBT E005)."""
    parts = (wmbt_urn or "").split(":")
    if len(parts) != 3 or parts[0] != "wmbt":
        raise AuthorInputError("wmbt", f"invalid wmbt urn {wmbt_urn!r}; expected wmbt:<wagon>:<CODE>")
    wagon_slug, code = parts[1], parts[2]
    plan = _plan_root(root)
    path = plan / _slug_to_dir(wagon_slug) / f"{code}.yaml"
    if not path.exists():
        raise AuthorInputError("wmbt", f"target WMBT {wmbt_urn!r} not found at {path}")
    acc_urn = (block.get("identity") or {}).get("urn")
    if not acc_urn:
        raise AuthorInputError("identity", "acceptance block missing identity.urn")
    if (block.get("identity") or {}).get("phase") not in ("GREEN", "SMOKE", "RED", "REFACTOR"):
        raise AuthorInputError("phase", "acceptance phase must be one of GREEN/SMOKE/RED/REFACTOR")
    # Schema gate BEFORE any write, so a rejected block leaves the file untouched.
    _validate_embedded_acceptance(block)

    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    accs = doc.setdefault("acceptances", [])
    if not any((a.get("identity") or {}).get("urn") == acc_urn for a in accs):
        accs.append(block)
        _write_yaml(path, doc)
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
    cn.add_argument("--statement", default="", help="one-sentence rule statement")
    cn.add_argument("--rationale", default=None, help="why this convention exists (spec §5.3, optional)")
    cn.add_argument("--note", dest="notes", default=None, help="optional clarification (spec §5.3 notes)")
    cn.add_argument(
        "--term", action="append", default=[], dest="terms",
        help="a term as 'term_id=text' (repeatable)",
    )
    cn.add_argument("--name", default=None, help="human-readable name")
    cn.add_argument("--implementation", default=None,
                    help="JSON object {type, ref} — the validator binding (ref = 'file::test')")
    cn.add_argument("--content", default=None,
                    help="JSON object: summary/normative_text/operational_guidance/examples/"
                         "counter_examples/constraints/exceptions/fix_hint")
    cn.add_argument("--bidirectional", default=None, help="JSON array of bidirectional refs")
    cn.add_argument("--metadata", default=None,
                    help="JSON object: aliases/severity/disposition/introduced_in/suppression_deadline")
    cn.add_argument("--node-source", dest="node_source", default=None,
                    help="JSON object: legacy_path/legacy_section/legacy_rule_id/legacy_sha/extraction_mode")
    cn.add_argument("--parity", default=None,
                    help="JSON object: *_preserved flags + reviewed_at (extraction parity)")
    cn.add_argument("--validation", default=None,
                    help="JSON object (#1247): optional validator-family intent — "
                         "family/template/variant, phase/enforcement, subject_kind, "
                         "selector/traversal/invariant, failure_evidence, config. "
                         "family/(family,template) checked against registry.yaml; "
                         "must carry no concrete runtime state")
    # Variant scaffolding (#1212): when a registered (family, template) pair is
    # given AND the rule carries an implementation binding, also scaffold the
    # convention-graph variant so the new convention is enforced, not just declared.
    cn.add_argument("--family", default=None,
                    help="convention-graph family to scaffold a variant under (with --template)")
    cn.add_argument("--template", default=None,
                    help="family template the scaffolded variant instantiates (with --family)")

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

    # `issue` — author / validate a GitHub issue BODY from issue.schema.json
    # (#1223). Peer of the other authored kinds; schema-driven generation +
    # the schema-driven compliance gate (--check). Planner-side + coach-free.
    iss = sub.add_parser("issue", help="author a schema-valid issue body, publish it store-first, or revise an existing issue")
    iss.add_argument("--title", default=None, help="issue title (the H1 + Problem Statement subject)")
    iss.add_argument("--slug", default=None,
                     help="work_item slug (the store uid); derived from --title when omitted (#1272)")
    iss.add_argument("--type", default=None, dest="issue_type",
                     help="issue Type (e.g. implementation, bug, refactor)")
    # default=None, not "INIT": the revise path must be able to tell "--status
    # was supplied" from "--status was omitted" so it can refuse the former
    # (#1661). The create path applies the INIT default itself.
    iss.add_argument("--status", default=None,
                     help="initial Status (phase-machine vocabulary: INIT/PLANNED/RED/...); default INIT")
    iss.add_argument("--branch", default=None, help="the issue's worktree branch")
    iss.add_argument("--train", default=None, help="train id the issue belongs to")
    iss.add_argument("--feature", default=None, help="feature urn the issue lands")
    iss.add_argument("--check", default=None, metavar="PATH",
                     help="validate an existing body file against issue.schema.json (no generation)")
    iss.add_argument("--revise", type=int, metavar="ISSUE",
                     help="revise an existing store-registered GitHub issue number")
    iss.add_argument("--body-file", default=None, metavar="PATH",
                     help="replacement issue body markdown for --revise")
    # #1309: the one capability the removed `atdd issue <slug> --dry-run` had and
    # nothing else covered — render + validate + print, writing NOTHING. `--check`
    # only validates an existing FILE, and a bare `atdd author issue` publishes
    # store-first, so neither is a dry run.
    iss.add_argument("--dry-run", action="store_true", dest="dry_run",
                     help="render the body and validate it, print it, and write nothing (no store, no gh)")

    # Plan-layer kinds — spec-driven (rich nested shape: produce[], components{},
    # wmbts[], acceptances[]). The spec file holds the same input dict the
    # create_<kind> functions accept; #1139 (atdd plan) writes it per locked unit.
    for _kind in ("wagon", "feature", "wmbt", "train", "interlocking", "contract"):
        pk = sub.add_parser(_kind, help=f"author a {_kind} (plan layer)")
        pk.add_argument("--spec", required=True, help="path to a YAML/JSON file with the kind's input dict")
        pk.add_argument("--root", default=None, help="repo root the plan/ home resolves against (default: cwd)")
    pa = sub.add_parser("acceptance", help="append an acceptance into an existing WMBT (plan layer)")
    pa.add_argument("--wmbt", required=True, dest="wmbt_urn", help="target WMBT urn (wmbt:<wagon>:<CODE>)")
    pa.add_argument("--spec", required=True, help="path to a YAML/JSON file with the acceptance block")
    pa.add_argument("--root", default=None, help="repo root the plan/ home resolves against (default: cwd)")

    # `extension init` / `workspace init` — scaffold a new package (P002).
    ext = sub.add_parser("extension", help="extension package operations")
    ext_sub = ext.add_subparsers(dest="subcmd", required=True)
    ei = ext_sub.add_parser("init", help="scaffold a new extension package")
    ei.add_argument("--extension", required=True, dest="extension_id",
                    help="<publisher>.extension.<persona>.<name> (persona: planner|tester|coder|coach)")
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

    impl = sub.add_parser("implementation", help="validator implementation operations")
    impl_sub = impl.add_subparsers(dest="subcmd", required=True)
    ii = impl_sub.add_parser("init", help="scaffold a compliant validator implementation (by construction)")
    ii.add_argument("--id", required=True, dest="implementation_id",
                    help="implementation_id (a family name, or a rule_id for a singleton)")
    ii.add_argument("--targets-workspace", required=True, dest="targets_workspace",
                    help="<publisher>.workspace.<name> the validator runs inside")
    ii.add_argument("--emits", action="append", required=True, dest="emits_rule_ids",
                    help="a rule_id this validator emits (repeatable; more than one = a FAMILY)")
    ii.add_argument("--dest", default="implementations",
                    help="package subdir to scaffold under (default: implementations)")
    ii.add_argument("--root", default=None, help="repo root (default: cwd)")

    return parser


def _parse_terms(raw_terms: list[str]) -> list[dict]:
    out = []
    for raw in raw_terms:
        tid, _, text = raw.partition("=")
        out.append({"term_id": tid.strip(), "text": text.strip()})
    return out


def _variant_request(args, implementation: dict | None) -> tuple[str, str, str] | None:
    """Resolve+validate a variant scaffold request from convention-node args.

    Returns ``(family, template, implementation_ref)`` when scaffolding is asked
    for, ``None`` when no --family/--template was given. Raises
    ``AuthorInputError`` (so the operator is told why) when the flags are
    half-given or the rule carries no ``implementation.ref`` binding. Called
    *before* the node is written so a bad request never leaves a stray node.
    """
    family = getattr(args, "family", None)
    template = getattr(args, "template", None)
    if family is None and template is None:
        return None
    if not (family and template):
        raise AuthorInputError(
            "family" if not family else "template",
            "--family and --template must be given together to scaffold a variant",
        )
    ref = (implementation or {}).get("ref")
    if not ref:
        raise AuthorInputError(
            "implementation",
            "--family/--template scaffolding requires --implementation with a 'ref' "
            "(the validator binding the variant enforces)",
        )

    from atdd.planner.commands.author_variant import validate_family_template

    validate_family_template(family, template)  # reject unknown pair before any write
    return family, template, ref


def _config_extensions(root: Path) -> list[str]:
    """Active authoring extensions from .atdd/config.yaml (author.extensions)."""
    cfg = Path(root) / ".atdd" / "config.yaml"
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        return list(((data.get("author") or {}).get("extensions")) or [])
    except Exception as exc:
        logger.debug("no usable author config", extra={"error": str(exc)})
        return []


def _json_arg(field: str, raw):
    """Parse a ``--flag`` whose value is a JSON document."""
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise AuthorInputError(field, f"--{field} must be valid JSON: {exc}")


def _print_violations(headline: str, violations: list) -> int:
    """Report schema violations on stderr; returns the schema-invalid exit code."""
    print(headline, file=sys.stderr)
    for v in violations:
        print(f"  - {v}", file=sys.stderr)
    return 1


def _run_merge_driver(args) -> int:
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


def _run_init_package(args) -> int:
    """`init` scaffolds a NEW package boundary, so it needs no authoring context
    (it creates the package the other kinds then write into) — P002."""
    from atdd.planner.commands.author_init import (
        init_extension_package, init_implementation_package, init_workspace_package,
    )

    root = Path(args.root) if getattr(args, "root", None) else Path(os.getcwd())
    try:
        if args.cmd == "extension":
            pkg = init_extension_package(
                args.extension_id, role=args.role,
                flow_wagon=args.flow_wagon, feature=args.feature, root=root,
            )
        elif args.cmd == "implementation":
            pkg = init_implementation_package(
                args.implementation_id, targets_workspace=args.targets_workspace,
                emits_rule_ids=args.emits_rule_ids, root=root, dest=args.dest,
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


def _run_issue_check(args) -> int:
    try:
        body = Path(args.check).read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("atdd author issue cannot read --check", extra={"path": args.check, "error": str(exc)})
        print(f"atdd author issue: cannot read {args.check}: {exc}", file=sys.stderr)
        return 2
    violations = validate_issue_body(body)
    if violations:
        return _print_violations(
            f"atdd author issue: {args.check} is not schema-valid:", violations
        )
    print(f"atdd author issue: {args.check} is schema-valid")
    return 0


def _revision_violations(body, issue_type) -> list:
    """Schema + type-agreement violations for a `--revise` request."""
    violations: list[str] = []
    if body is not None:
        violations.extend(validate_issue_body(body))
        body_type = extract_issue_type(body)
        if issue_type is not None and body_type is not None and body_type != issue_type:
            violations.append(
                f"body Type {body_type!r} does not match explicit --type "
                f"{issue_type!r}"
            )
    if issue_type is not None and issue_type not in issue_type_enum():
        violations.append(
            f"invalid --type {issue_type!r}: not in the issue type "
            f"vocabulary ({', '.join(issue_type_enum())})"
        )
    return violations


def _print_revise_outcome(result) -> None:
    if result.projection_deferred:
        print(
            f"atdd author issue: revised work_item {result.slug!r} "
            f"(state={result.state}) for github #{result.issue_number}; "
            "github projection deferred to the outbox",
            file=sys.stderr,
        )
    else:
        print(
            f"atdd author issue: revised work_item {result.slug!r} "
            f"(state={result.state}) for github #{result.issue_number}",
            file=sys.stderr,
        )


def _read_issue_body_file(path: str):
    """``(body, None)`` for the text at ``path``; ``(None, 2)`` when it cannot be
    read (the caller returns that exit code)."""
    try:
        return Path(path).read_text(encoding="utf-8"), None
    except OSError as exc:
        logger.warning(
            "atdd author issue cannot read --body-file",
            extra={"path": path, "error": str(exc)},
        )
        print(
            f"atdd author issue: cannot read {path}: {exc}",
            file=sys.stderr,
        )
        return None, 2


def _publish_revision(args, body) -> int:
    from atdd.planner.commands.author_publish import PublishError, revise_issue

    try:
        result = revise_issue(
            args.revise,
            body=body,
            issue_type=args.issue_type,
            feature=args.feature,
            title=args.title,
        )
    except PublishError as exc:
        logger.warning(
            "atdd author issue revision failed",
            extra={"issue_number": args.revise, "error": str(exc)},
        )
        print(f"atdd author issue: {exc}", file=sys.stderr)
        return 2

    if body is not None:
        sys.stdout.write(body)
    if args.feature:
        # Name the binding that landed. Without this an operator cannot tell a
        # successful write from a silently-ignored flag — the ambiguity that let
        # Break 4 survive eight measured revisions (#1635).
        print(
            f"atdd author issue: feature binding set to {args.feature}",
            file=sys.stderr,
        )
    if args.title:
        print(
            f"atdd author issue: title set to {args.title!r}",
            file=sys.stderr,
        )
    _print_revise_outcome(result)
    return 0


# Flags the `issue` parser registers that the revise path defines no semantics
# for (#1661). Each is REFUSED by name rather than accepted and discarded: a
# flag that looks written is the hazard, matching the fail-closed posture of
# manifest_migration (refuses a whole run over a half-valid corpus) and
# extensions_lock (aborts before opening the file, because a half-written lock
# looks pinned). The set is pinned by a test — widening it to silence a newly
# dropped flag is a visible, reviewable act, not a quiet one.
_REVISE_UNSUPPORTED: tuple[tuple[str, str, str], ...] = (
    ("slug", "--slug", "the work item's uid, which a revision does not move"),
    ("status", "--status", "owned by the phase machine; use `atdd coach transition <N> <STATUS>`"),
    ("branch", "--branch", "create-time metadata; set it when the issue is authored"),
    ("train", "--train", "create-time metadata; set it when the issue is authored"),
)


def _refused_revise_flags(args) -> list[str]:
    """Messages for every unsupported flag this revise request supplied."""
    return [
        f"atdd author issue: --revise cannot honour {flag} ({why})"
        for dest, flag, why in _REVISE_UNSUPPORTED
        if getattr(args, dest, None) is not None
    ]


def _run_issue_revise(args) -> int:
    # Refuse BEFORE any validation or write. A flag this path cannot honour must
    # stop the command, not be dropped on the way to a store write that then
    # reports success (#1661).
    refusals = _refused_revise_flags(args)
    if refusals:
        for message in refusals:
            print(message, file=sys.stderr)
        print(
            "atdd author issue: nothing was written; re-run without the flags "
            "above, or use the command named beside each one",
            file=sys.stderr,
        )
        return 2

    # `--feature` alone is a valid revision (#1635), and so is `--title` alone
    # (#1661). Neither previously was: the precondition demanded --body-file
    # and/or --type, so an operator correcting only a wrong binding or a wrong
    # title was turned away — and when they satisfied it by also passing
    # --body-file, the value was silently dropped further down.
    if (
        args.body_file is None
        and args.issue_type is None
        and args.feature is None
        and args.title is None
    ):
        print(
            "atdd author issue: --revise requires --body-file, --feature, "
            "--title and/or explicit --type",
            file=sys.stderr,
        )
        return 2

    body = None
    if args.body_file is not None:
        body, err = _read_issue_body_file(args.body_file)
        if err is not None:
            return err

    violations = _revision_violations(body, args.issue_type)
    if violations:
        return _print_violations(
            "atdd author issue: revised issue body/type is not schema-valid:", violations
        )

    if getattr(args, "dry_run", False):
        if body is not None:
            sys.stdout.write(body)
        else:
            print(
                f"atdd author issue: revision for github #{args.revise} "
                "is schema-valid"
            )
        return 0

    return _publish_revision(args, body)


def _print_publish_outcome(slug: str, result) -> None:
    if result.projection_deferred:
        print(
            f"atdd author issue: published work_item {slug!r} (state={result.state}); "
            "github projection deferred to the outbox (durable retry)",
            file=sys.stderr,
        )
    else:
        print(
            f"atdd author issue: published work_item {slug!r} (state={result.state}) "
            f"-> github #{result.github_number}",
            file=sys.stderr,
        )


def _run_issue_create(args) -> int:
    issue_type = args.issue_type or "implementation"
    # The parser no longer carries the INIT default (#1661) so that --revise can
    # distinguish supplied from omitted; the create path applies it here.
    status = args.status or "INIT"
    spec = {
        "title": args.title,
        "status": status,
        "type": issue_type,
        "branch": args.branch,
        "train": args.train,
        "feature": args.feature,
    }
    body = create_issue_body({k: v for k, v in spec.items() if v is not None})

    # #1309: `--dry-run` returns BEFORE the publish import, so no store
    # connection is opened and no gh call is made. Inherited from the removed
    # `atdd issue <slug> --dry-run` (E019), whose smoke coverage retargets here.
    if getattr(args, "dry_run", False):
        violations = validate_issue_body(body)
        if violations:
            return _print_violations(
                "atdd author issue: rendered body is not schema-valid:", violations
            )
        print(body)
        return 0

    # #1272: authoring PUBLISHES store-first by default (no extra flag). The
    # store is authoritative — write it BEFORE emitting the body. Only if the
    # store write succeeds do we print the body; a store failure fails loud
    # (no body-only degrade — the exact gap that orphaned #1271).
    from atdd.planner.commands.author_publish import (
        PublishError, derive_slug, publish_issue,
    )

    slug = args.slug or derive_slug(args.title or "")
    try:
        result = publish_issue(
            slug, body,
            title=args.title or "Untitled ATDD issue",
            status=status, issue_type=issue_type,
            branch=args.branch, train=args.train, feature=args.feature,
        )
    except PublishError as exc:
        logger.warning("atdd author issue publish failed", extra={"slug": slug, "error": str(exc)})
        print(f"atdd author issue: {exc}", file=sys.stderr)
        return 2

    # Store write succeeded — the body is now authoritative in the store.
    # Emit it on stdout (preserves the body-authoring contract), and report
    # the publish outcome on stderr.
    print(body)
    _print_publish_outcome(slug, result)
    return 0


def _run_issue(args) -> int:
    """`issue` authors/validates a body string (stdout); it writes no file and
    needs no authoring-context resolution — dispatched before resolve_context."""
    if args.check is not None:
        return _run_issue_check(args)
    if args.revise is not None:
        return _run_issue_revise(args)
    return _run_issue_create(args)


def _create_plan_artifact(args, spec):
    """Dispatch to the ``create_*`` owning the requested plan-layer kind."""
    if args.cmd == "wagon":
        return create_wagon(spec, root=args.root)
    if args.cmd == "feature":
        return create_feature(spec, root=args.root)
    if args.cmd == "wmbt":
        return create_wmbt(spec, root=args.root)
    if args.cmd == "train":
        return create_train(spec, root=args.root)
    if args.cmd == "interlocking":
        return create_interlocking(spec, root=args.root)
    if args.cmd == "contract":
        return create_contract(spec, root=args.root)
    return create_acceptance(args.wmbt_urn, spec, root=args.root)  # acceptance


def _run_plan_kind(args) -> int:
    """Plan-layer kinds write under plan/ (not core/extension), so they need no
    authoring-context resolution — dispatched before resolve_context."""
    from atdd.planner.interlocking import InterlockingError
    try:
        spec = yaml.safe_load(Path(args.spec).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("atdd author cannot read --spec", extra={"path": args.spec, "error": str(exc)})
        print(f"atdd author: cannot read --spec: {exc}", file=sys.stderr)
        return 2
    try:
        out = _create_plan_artifact(args, spec)
    except AuthorInputError as exc:
        logger.warning("atdd author rejected input", extra={"field": getattr(exc, "field", None)})
        print(f"atdd author: {exc}", file=sys.stderr)
        return 2
    except InterlockingError as exc:
        logger.warning(
            "atdd author interlocking precondition unmet",
            extra={"error": str(exc)},
        )
        print(f"atdd author: {exc}", file=sys.stderr)
        return 2
    print(str(out))
    return 0


def _scaffold_variant_if_requested(variant_req, rule_id: str, root):
    """Scaffold the variant a convention-node requested, if it requested one."""
    if variant_req is None:
        return None
    from atdd.planner.commands.author_variant import scaffold_variant

    family, template, ref = variant_req
    return scaffold_variant(
        family=family, template=template, rule_id=rule_id,
        implementation_ref=ref, root=root,
    )


def _convention_node_role(args, ctx):
    """The role owning the node: explicit for core, derived from the rule_id for
    an extension. Returns None when --core was given without --role."""
    if not ctx.is_core:
        return args.rule_id.split(".", 1)[0]  # extension: derive role from rule_id
    return args.role or None


def _run_convention_node(args, ctx, root) -> int:
    from atdd.planner.commands.author_context import node_home

    role = _convention_node_role(args, ctx)
    if role is None:
        print("atdd author: --core convention-node requires --role", file=sys.stderr)
        return 2
    path = node_home(ctx, role, args.rule_id, root)
    try:
        implementation = _json_arg("implementation", getattr(args, "implementation", None))
        variant_req = _variant_request(args, implementation)  # validate before any write
        create_convention_node(
            role, args.rule_id, kind=args.kind, status=args.status,
            statement=args.statement, name=getattr(args, "name", None),
            rationale=args.rationale, notes=args.notes,
            implementation=implementation,
            source=_json_arg("node-source", getattr(args, "node_source", None)),
            content=_json_arg("content", getattr(args, "content", None)),
            bidirectional=_json_arg("bidirectional", getattr(args, "bidirectional", None)),
            metadata=_json_arg("metadata", getattr(args, "metadata", None)),
            parity=_json_arg("parity", getattr(args, "parity", None)),
            validation=_json_arg("validation", getattr(args, "validation", None)),
            terms=_parse_terms(args.terms), path=path,
        )
        variant_path = _scaffold_variant_if_requested(variant_req, args.rule_id, root)
    except AuthorInputError as exc:
        logger.warning("atdd author rejected input", extra={"field": getattr(exc, "field", None)})
        print(f"atdd author: {exc}", file=sys.stderr)
        return 2
    print(str(path))
    if variant_path is not None:
        print(str(variant_path))
    return 0


def _run_relationship(args, ctx, root) -> int:
    from atdd.planner.commands.author_context import relationship_graph_id, relationship_home
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


def _run_scope(args, ctx, root) -> int:
    from atdd.planner.commands.author_context import scope_home
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


def _run_gate(args, ctx, root) -> int:
    from atdd.planner.commands.author_context import gate_home
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


# Author kinds that write under plan/ rather than a core/extension package.
_PLAN_KINDS = ("wagon", "feature", "wmbt", "train", "interlocking", "contract", "acceptance")
# Author kinds that scaffold a new package boundary.
_PACKAGE_KINDS = ("extension", "workspace", "implementation")
# Kinds dispatched AFTER an authoring context is resolved (P001, spec §6).
_CONTEXTUAL_RUNNERS = {
    "convention-node": _run_convention_node,
    "relationship": _run_relationship,
    "scope": _run_scope,
    "gate": _run_gate,
}


def run(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    # These kinds need no authoring-context resolution — dispatch before it.
    if args.cmd == "merge-driver":
        return _run_merge_driver(args)
    if args.cmd in _PACKAGE_KINDS:
        return _run_init_package(args)
    if args.cmd == "issue":
        return _run_issue(args)
    if args.cmd in _PLAN_KINDS:
        return _run_plan_kind(args)

    runner = _CONTEXTUAL_RUNNERS.get(args.cmd)
    if runner is None:
        return 2

    # every author kind resolves an authoring context first (P001, spec §6).
    from atdd.planner.commands.author_context import resolve_context

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

    return runner(args, ctx, root)
