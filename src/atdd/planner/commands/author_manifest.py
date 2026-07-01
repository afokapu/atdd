# Component: component:author-atdd-substrate:substrate-spine:AuthorManifest:backend:application
"""Package-manifest validators + the provider↔implementation contract (C006).

Validate the three package manifests — extension (`atdd.extension.yaml`),
workspace provider (`atdd.workspace.yaml`), and implementation
(`atdd.implementation.yaml`) — and the versioned CONTRACT that ties them
together: a provider declares a concrete ``contract_version``; an extension and
an implementation declare the range/version they target; the resolver checks
SemVer compatibility and refuses on mismatch.

Reuses the namespace guards (``validate_extension_id`` / ``validate_workspace_id``)
so an id is never validated two different ways.
"""
from __future__ import annotations

import re

from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_context import (
    validate_extension_id,
    validate_workspace_id,
)

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
# Supported ranges: exact (1.0.0), caret (^1.0.0), tilde (~1.0.0), >= (>=1.0.0),
# and x-ranges (1.x / 1.2.x). Compound ranges are intentionally unsupported in V1.
_RANGE_RE = re.compile(
    r"^(?P<op>\^|~|>=|=)?\s*(?P<maj>\d+)\.(?P<min>\d+|x|\*)(?:\.(?P<pat>\d+|x|\*))?$"
)
_RUNTIME_KEYS = ("language", "runner", "command")

# ── Capability-based workspace contract (#1138) ─────────────────────────────
# A workspace provides one or more typed CAPABILITIES. `domain` is a small closed
# controlled vocabulary; `type` is package-specific; `contract` is a versioned ATDD
# contract that defines the capability's required fields. Required fields are validated
# from the CONTRACT, not from the domain.
_CAPABILITY_DOMAINS = frozenset({
    "execution",        # runs commands/tests/validators/fixers/generators
    "environment",      # provides the execution context / isolation boundary
    "source_control",   # VCS / commit / branch / trailer mechanics
    "transport",        # moves messages/commands/events between systems/agents
    "orchestration",    # manages sessions/processes/agent lifecycle/routing
    "artifact",         # reads/writes reports, build outputs, logs, generated files
    "security",         # credentials, policy, permission, command allow/deny
    "observability",    # traces, logs, telemetry, runtime evidence
})


def _check_execution_command_runner(cap: dict) -> None:
    rt = cap.get("runtime") or {}
    for key in _RUNTIME_KEYS:
        if not rt.get(key):
            raise AuthorInputError("capabilities", f"execution capability runtime missing {key!r}")


def _check_scm_commit_trailers(cap: dict) -> None:
    if cap.get("vcs") != "git":
        raise AuthorInputError("capabilities", "source_control commit-trailers capability requires vcs: git")


# contract id -> required-field validator (the AUTHORITATIVE per-capability schema).
_CAPABILITY_CONTRACTS = {
    "atdd.workspace.capability.execution.command-runner.v1": _check_execution_command_runner,
    "atdd.workspace.capability.environment.isolation.v1": lambda cap: None,
    "atdd.workspace.capability.source-control.commit-trailers.v1": _check_scm_commit_trailers,
    "atdd.workspace.capability.transport.command-feed.v1": lambda cap: None,
    "atdd.workspace.capability.orchestration.agent-session.v1": lambda cap: None,
}


def _validate_capability(cap: dict) -> None:
    if not isinstance(cap, dict):
        raise AuthorInputError("capabilities", "each capability must be a mapping")
    for field in ("capability_id", "domain", "type", "contract"):
        if not cap.get(field):
            raise AuthorInputError("capabilities", f"capability missing {field!r}")
    domain = cap["domain"]
    if domain == "experimental":
        return  # escape hatch: core does not validate experimental capabilities
    if domain not in _CAPABILITY_DOMAINS:
        raise AuthorInputError("capabilities", f"unknown capability domain {domain!r}")
    check = _CAPABILITY_CONTRACTS.get(cap["contract"])
    if check is None:
        raise AuthorInputError("capabilities", f"unknown capability contract {cap['contract']!r}")
    check(cap)


def _parse_version(value, *, field: str = "contract_version") -> tuple[int, int, int]:
    m = _SEMVER_RE.match(str(value or ""))
    if not m:
        raise AuthorInputError(
            field, f"invalid version {value!r}; expected concrete MAJOR.MINOR.PATCH"
        )
    return tuple(int(x) for x in m.groups())  # type: ignore[return-value]


def _parse_range(spec, *, field: str = "contract") -> re.Match:
    m = _RANGE_RE.match(str(spec or "").strip())
    if not m:
        raise AuthorInputError(
            field,
            f"invalid contract range {spec!r}; expected e.g. ^1.0.0, ~1.2.0, 1.0.0, 1.x",
        )
    return m


def contract_satisfies(version: str, spec: str) -> bool:
    """True if concrete SemVer ``version`` satisfies range ``spec``.

    Supports exact (``1.0.0``), caret (``^1.0.0`` — same major, ≥ base), tilde
    (``~1.0.0`` — same major+minor, ≥ base), ``>=``, and x-ranges (``1.x`` /
    ``1.2.x``). Raises ``AuthorInputError`` if either side is malformed.
    """
    cur = _parse_version(version)
    m = _parse_range(spec)
    op = m.group("op") or "="
    rmaj = int(m.group("maj"))
    rmin_raw, rpat_raw = m.group("min"), m.group("pat")

    if rmin_raw in ("x", "*"):
        return cur[0] == rmaj
    rmin = int(rmin_raw)
    if rpat_raw in ("x", "*"):
        return cur[0] == rmaj and cur[1] == rmin
    base = (rmaj, rmin, int(rpat_raw) if rpat_raw is not None else 0)

    if op == ">=":
        return cur >= base
    if op == "^":
        return cur[0] == rmaj and cur >= base
    if op == "~":
        return cur[0] == rmaj and cur[1] == rmin and cur >= base
    return cur == base  # exact


def validate_workspace_manifest(data: dict) -> None:
    """Validate an ``atdd.workspace.yaml`` provider manifest.

    Capability-based (#1138): a workspace declares one or more typed CAPABILITIES; an
    execution runner is just one capability, not the definition of a workspace.
    ``runtime.{language,runner,command}`` is required only for an execution capability —
    an isolation/transport/orchestration provider needs no runner. The legacy
    top-level-``runtime`` shape is still accepted (treated as one execution capability)
    so providers migrate without breaking the composition gate.
    """
    data = data or {}
    if data.get("kind") != "workspace":
        raise AuthorInputError("kind", "workspace manifest must have kind: workspace")
    validate_workspace_id(data.get("workspace_id", ""), allow_reserved=True)

    capabilities = data.get("capabilities")
    if not capabilities and data.get("runtime"):
        # legacy back-compat: a top-level runtime is one implicit execution capability
        capabilities = [{
            "capability_id": "execution.legacy",
            "domain": "execution",
            "type": "command-runner",
            "contract": "atdd.workspace.capability.execution.command-runner.v1",
            "runtime": data["runtime"],
        }]
        _parse_version(data.get("contract_version"))  # legacy contract_version stays required

    if not capabilities:
        raise AuthorInputError("capabilities", "workspace must declare at least one capability")
    if data.get("capabilities") and data.get("contract_version") is not None:
        _parse_version(data["contract_version"])  # capability-mode: contract_version is optional
    for cap in capabilities:
        _validate_capability(cap)

    discovers = data.get("discovers") or {}  # optional; validated only for shape
    if discovers.get("requires_contract") is not None:
        _parse_range(discovers["requires_contract"], field="requires_contract")


def validate_extension_manifest(data: dict) -> None:
    """Validate an ``atdd.extension.yaml`` use-case manifest."""
    if (data or {}).get("kind") != "extension":
        raise AuthorInputError("kind", "extension manifest must have kind: extension")
    validate_extension_id(data.get("extension_id", ""), allow_reserved=True)
    if not isinstance(data.get("owns"), dict):
        raise AuthorInputError("owns", "extension manifest must have an owns mapping")
    # realizes (#1133): optional cross-package linkage — each entry maps an
    # extension node onto the core node it realizes. Shape-only here; resolution +
    # ownership are checked at composition time (compose.validate_realizes).
    for entry in (data.get("realizes") or []):
        if not isinstance(entry, dict) or not entry.get("extension_node") or not entry.get("core_node"):
            raise AuthorInputError(
                "realizes", "each realizes entry must be a mapping {extension_node, core_node}"
            )
    for entry in ((data.get("depends_on") or {}).get("workspaces") or []):
        if not isinstance(entry, dict):
            raise AuthorInputError(
                "depends_on", "each depends_on.workspaces entry must be a mapping {id, contract}"
            )
        validate_workspace_id(entry.get("id", ""), allow_reserved=True)
        _parse_range(entry.get("contract"), field="depends_on")


def validate_implementation_manifest(data: dict) -> None:
    """Validate an ``atdd.implementation.yaml`` manifest — the VALIDATOR/FAMILY contract.

    Beyond identity (kind/id/targets/contract), enforces the executable-validator
    shape so a validator is compliant *by construction* rather than by copying an
    example: a runnable ``entrypoint``, a v1.1 ``report`` emitter, and a non-empty
    ``emits_rule_ids`` list (the rule_ids this one detector realizes — a FAMILY
    detector emits >1, a singleton emits 1). ``realizes_convention`` (the primary
    node) and ``subtype`` are validated for consistency when present. This is the
    ``atdd.core.implementation-schema`` every extension declares in ``depends_on``.
    """
    data = data or {}
    if data.get("kind") != "implementation":
        raise AuthorInputError("kind", "implementation manifest must have kind: implementation")
    if not data.get("implementation_id"):
        raise AuthorInputError("implementation_id", "implementation manifest missing implementation_id")
    validate_workspace_id(data.get("targets_workspace", ""), allow_reserved=True)
    _parse_version(data.get("contract_version"))

    if not (isinstance(data.get("entrypoint"), str) and data["entrypoint"].strip()):
        raise AuthorInputError("entrypoint", "implementation must declare an entrypoint (the detector module)")
    report = data.get("report")
    if report is not None and not (isinstance(report, str) and report.strip()):
        raise AuthorInputError(
            "report",
            "report, when declared, must be a non-empty path (the runnable v1.1 report-emitter "
            "the provider CLI collects; may equal entrypoint)")
    # The impl must declare the rule_id(s) it realizes — via a non-empty
    # ``emits_rule_ids`` list (v1.1; a FAMILY detector emits >1 from one run) OR a
    # single ``realizes_convention`` (v1.0 exit-code mapping). At least one required.
    emits = data.get("emits_rule_ids")
    rc = data.get("realizes_convention")
    has_emits = isinstance(emits, list) and bool(emits)
    if has_emits and not all(isinstance(r, str) and r.strip() for r in emits):
        raise AuthorInputError("emits_rule_ids", "emits_rule_ids entries must be non-empty rule_id strings")
    has_rc = isinstance(rc, str) and bool(rc.strip())
    if not has_emits and not has_rc:
        raise AuthorInputError(
            "emits_rule_ids",
            "implementation must declare the rule_id(s) it realizes — a non-empty emits_rule_ids "
            "list (v1.1; a FAMILY emits more than one) or realizes_convention (v1.0 single-rule)")
    if has_emits and has_rc and rc not in emits:
        raise AuthorInputError(
            "realizes_convention", f"realizes_convention {rc!r} must be one of emits_rule_ids {emits!r}")
    sub = data.get("subtype")
    if sub is not None and sub != "validator":
        raise AuthorInputError("subtype", f"implementation subtype must be 'validator' (got {sub!r})")


def extension_targets_satisfied_by(ext_manifest: dict, provider_manifest: dict) -> bool:
    """True if the provider's contract_version satisfies the extension's range for it."""
    pid = provider_manifest.get("workspace_id")
    pver = provider_manifest.get("contract_version")
    for entry in ((ext_manifest.get("depends_on") or {}).get("workspaces") or []):
        if entry.get("id") == pid and not contract_satisfies(pver, entry.get("contract")):
            return False
    return True


def implementation_accepted_by(impl_manifest: dict, provider_manifest: dict) -> bool:
    """True if the implementation's contract_version satisfies the provider's requires_contract."""
    req = (provider_manifest.get("discovers") or {}).get("requires_contract")
    if not req:
        return True
    return contract_satisfies(impl_manifest.get("contract_version"), req)
