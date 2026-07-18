# URN: component:enforce-binding-plan:run-binding-plan:scan-policy:backend:domain
# Runtime: python
# Purpose: Join severity/disposition from the convention node + compute per-rule
#          scan roots/excludes (rule>role>default), incl. the dogfood print
#          exemption of src/atdd.
"""Convention metadata join + scan policy (#1238 phase ``scan-policy-and-parity``).

Two provider-agnostic concerns the runner needs, both pure data:

* :func:`rule_metadata` — read ``metadata.severity`` / ``metadata.disposition``
  off a bound rule's vendored convention node. The provider emits no severity;
  the runner joins it here so the disposition verdict can be computed.
* :func:`compute_scan_policy` — resolve a rule's repo-relative scan roots +
  exclusion globs from ``.atdd/config.yaml`` (``scan`` block, rule > role >
  default precedence; excludes additive), with two built-ins:
    - an explicit ``--paths`` override replaces the configured roots for every
      rule (operator/CI scoping);
    - the ``coder.logging.print`` rule EXEMPTS the toolkit's own ``src/atdd``
      tree (ATDD is itself a CLI tool whose console output is the product
      surface — the legacy in-core validator exempts it the same way, V4).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Optional, Sequence

import yaml

from atdd.enforce.dispositions import STRICT, TREATMENT_DISPOSITIONS

_log = logging.getLogger(__name__)


class UnknownDispositionError(ValueError):
    """A convention node declares a ``metadata.disposition`` outside the treatment
    vocabulary (#1424 E002) — a wiring/authoring error, not a verdict."""

# Rules that exempt the toolkit's own CLI source tree. Mirrors the legacy
# in-core ``coder.logging.print`` exemption of ``src/atdd`` (V4 / scan_policy
# docstring of the cw prototype): ATDD's own ``print``s are product output.
_TOOLKIT_CLI_EXEMPT_RULES = frozenset({"coder.logging.print"})
_TOOLKIT_CLI_EXEMPT_RELPATH = "src/atdd"

# Per-rule DEFAULT exclusion globs — the legacy convention/validator exclusion
# carves the hermetic detectors relocated onto the caller (#1238 V4 parity, the
# "systemic relocation" cross-cutting finding 0 of docs/PARITY-AUDIT-26.md).
# Without re-supplying them here the extension OVER-SCANS relative to the legacy
# in-core validator (false positives in tests/migrations/validators/fixtures).
# Each list is ported VERBATIM from its legacy source (cited); the vendored
# detectors honor ``ATDD_SCAN_EXCLUDES`` (fnmatch against the scan-root-relative
# path), so these globs reproduce the legacy carve without touching the detector.
_RULE_DEFAULT_EXCLUDES: dict[str, tuple[str, ...]] = {
    # src/atdd/coder/conventions/security.convention.yaml
    #   security.rules.sql_injection.exclusions (verbatim)
    "coder.security.sql-injection": (
        "**/tests/**",
        "**/test_*.py",
        "**/conftest.py",
        "**/migrations/**",
    ),
    # src/atdd/coder/conventions/duplication.convention.yaml
    #   duplication.rules.intra_layer_duplication.exclusions (verbatim)
    "coder.duplication.no-intra-layer-code-python": (
        "**/tests/**",
        "**/test_*.py",
        "**/conftest.py",
        "**/__init__.py",
        "**/__pycache__/**",
        "**/migrations/**",
        "**/validators/**",
        "**/templates/**",
    ),
    # src/atdd/coder/validators/test_no_silent_exception_swallowing_python.py
    #   _is_excluded() — the relocated ``/fixtures/`` carve (the test-file/init
    #   carves are already applied by the detector's own test-file skip). The
    #   legacy substring ``"/fixtures/" in path`` becomes the scan-root-relative
    #   glob that bites any nested fixtures tree.
    "coder.logging.coach-silent-swallow": (
        "**/fixtures/**",
    ),
    # src/atdd/coder/validators/test_query_count.py
    #   find_python_files()/scan_query_count() — the relocated ``/migrations/``
    #   carve (legacy substring ``"/migrations/" in path``).
    "coder.refactor.nplus1": (
        "**/migrations/**",
    ),
}

# Rules whose reachability graph needs the consumer's CLI entry-point modules as
# extra graph ROOTS (not excludes): a module reachable only via a console script
# is not dead. Legacy ``find_cli_entry_points`` (test_dead_code_python.py L296)
# read pyproject ``[project.scripts]``; the hermetic detector dropped it
# ("NOT PORTED", dead_code_python.py docstring). The enforce layer re-supplies
# the resolved entry-point module files as scan-policy ``graph_roots`` so the
# detector stays hermetic (it consumes explicit roots, it does not parse
# pyproject itself). See docs/PARITY-AUDIT-26.md row 1 / REGRESSION #3.
_ENTRY_POINT_ROOT_RULES = frozenset({"coder.dead-code.reachability"})


@dataclass(frozen=True)
class RuleMetadata:
    rule_id: str
    severity: Optional[int]
    disposition: str  # a member of VOCABULARY (the TREATMENT namespace)

    #: The treatment disposition vocabulary (E002). A node whose
    #: ``metadata.disposition`` is outside this set is rejected by
    #: :func:`rule_metadata`. Sourced from the shared disposition model so the
    #: treatment namespace is named in exactly one place.
    VOCABULARY: ClassVar[frozenset] = TREATMENT_DISPOSITIONS


def _convention_node_path(substrate_home: Path, rule_id: str) -> Optional[Path]:
    """Locate ``<rule_id>.convention.yaml`` under the vendored extension trees."""
    ext_root = substrate_home / ".atdd" / "extensions"
    if not ext_root.is_dir():
        return None
    matches = sorted(ext_root.rglob(f"{rule_id}.convention.yaml"))
    return matches[0] if matches else None


def rule_metadata(substrate_home: Path, rule_id: str) -> RuleMetadata:
    """Read severity + disposition from a bound rule's convention node.

    Defaults to ``strict`` (and no severity) when the node is missing or carries
    no disposition — the same defensive default the disposition gate uses, so an
    unregistered rule fails closed rather than silently passing.
    """
    node = _convention_node_path(substrate_home, rule_id)
    if node is None:
        return RuleMetadata(rule_id=rule_id, severity=None, disposition="strict")
    try:
        data = yaml.safe_load(node.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        _log.warning(
            "unreadable convention node — defaulting to strict",
            extra={"node": str(node), "rule_id": rule_id, "error": str(exc)},
        )
        return RuleMetadata(rule_id=rule_id, severity=None, disposition="strict")
    meta = data.get("metadata") if isinstance(data, dict) else None
    meta = meta if isinstance(meta, dict) else {}
    sev = meta.get("severity")
    # A missing disposition defaults to strict (in-vocabulary); an explicitly
    # declared out-of-vocabulary value is REJECTED (#1424 E002) — a typo or a
    # stray wiring value must not fall through to the verdict mapping.
    disp = str(meta.get("disposition") or STRICT)
    if disp not in RuleMetadata.VOCABULARY:
        raise UnknownDispositionError(
            f"convention node {node} declares metadata.disposition {disp!r}, "
            f"outside the treatment vocabulary {sorted(RuleMetadata.VOCABULARY)}"
        )
    return RuleMetadata(
        rule_id=rule_id,
        severity=int(sev) if isinstance(sev, int) else None,
        disposition=disp,
    )


def _as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return []


def _archetype_of(rule_id: str) -> str:
    return rule_id.split(".", 1)[0] if rule_id else ""


def _resolve_root(repo_root: Path, root: str) -> Path:
    p = Path(root)
    return (p if p.is_absolute() else (repo_root / p)).resolve()


def _is_within(path: Path, base: Path) -> bool:
    # is_relative_to (3.9+) is a pure predicate — no exception-as-control-flow.
    return path == base or path.is_relative_to(base)


@dataclass(frozen=True)
class ScanPolicy:
    scan_roots: list[str]      # absolute, normalized
    scan_excludes: list[str]   # repo-relative globs, verbatim
    exempt: bool = False       # whole rule exempt for this repo (e.g. print over src/atdd)
    exempt_reason: str = ""
    # Extra graph ROOTS (absolute file paths) the reachability detector must treat
    # as live entry points — e.g. pyproject ``[project.scripts]`` modules. Empty
    # for every rule that does not use reachability roots.
    graph_roots: list[str] = field(default_factory=list)


def _parse_pyproject_script_modules(repo_root: Path) -> list[str]:
    """Extract ``[project.scripts]`` entry-point module paths from pyproject.toml.

    Ported VERBATIM from the legacy ``find_cli_entry_points``
    (src/atdd/coder/validators/test_dead_code_python.py L296-331): a minimal
    line scanner that reads the ``[project.scripts]`` table and takes the module
    path before the ``:`` of each ``name = "module.path:attr"`` entry. Returns
    dotted module strings (e.g. ``atdd.cli``).
    """
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return []
    try:
        content = pyproject.read_text(encoding="utf-8")
    except OSError as exc:
        _log.warning(
            "unreadable pyproject.toml — no entry-point roots",
            extra={"path": str(pyproject), "error": str(exc)},
        )
        return []
    in_scripts = False
    modules: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "[project.scripts]":
            in_scripts = True
            continue
        if in_scripts:
            if stripped.startswith("["):
                break
            if "=" in stripped:
                _, value = stripped.split("=", 1)
                value = value.strip().strip('"').strip("'")
                module = value.split(":")[0]
                if module:
                    modules.append(module)
    return modules


def _resolve_module_to_files(module: str, anchors: Sequence[Path]) -> list[Path]:
    """Resolve a dotted module to existing ``<anchor>/path.py`` or package init."""
    rel = Path(*module.split("."))
    out: list[Path] = []
    for anchor in anchors:
        py = (anchor / rel).with_suffix(".py")
        if py.is_file():
            out.append(py.resolve())
        init = anchor / rel / "__init__.py"
        if init.is_file():
            out.append(init.resolve())
    return out


def compute_graph_roots(
    repo_root: Path, rule_id: str, resolved_roots: Sequence[Path]
) -> list[str]:
    """Resolve CLI entry-point module files for a reachability rule (else ``[]``).

    The enforce layer parses the SCANNED tree's pyproject ``[project.scripts]``
    and resolves each entry module to a file under the scan roots (and the repo
    root, for a flat layout). Those files are the graph roots the legacy
    reachability validator seeded from console scripts; supplying them keeps the
    detector hermetic while restoring parity (REGRESSION #3).
    """
    if rule_id not in _ENTRY_POINT_ROOT_RULES:
        return []
    modules = _parse_pyproject_script_modules(repo_root)
    if not modules:
        return []
    anchors = list(dict.fromkeys([*resolved_roots, repo_root]))
    roots: list[str] = []
    for module in modules:
        for f in _resolve_module_to_files(module, anchors):
            s = str(f)
            if s not in roots:
                roots.append(s)
    return roots


def compute_scan_policy(
    repo_root: Path,
    config: dict,
    rule_id: str,
    *,
    path_override: Optional[Sequence[str]] = None,
) -> ScanPolicy:
    """Resolve ``{scan_roots, scan_excludes}`` for ``rule_id``.

    ``path_override`` (the ``--paths`` flag) replaces the configured roots for
    every rule. The ``coder.logging.print`` rule drops any root within
    ``src/atdd`` (the toolkit CLI exemption); if that leaves it with no roots, the
    rule is marked ``exempt`` so the runner skips it WITHOUT naming it as a
    violation (V4 — the exemption must be preserved).
    """
    scan = config.get("scan") if isinstance(config, dict) else None
    scan = scan if isinstance(scan, dict) else {}

    default_roots = _as_str_list(scan.get("roots")) or ["."]
    default_excludes = _as_str_list(scan.get("excludes"))
    roles = scan.get("roles") if isinstance(scan.get("roles"), dict) else {}
    rules = scan.get("rules") if isinstance(scan.get("rules"), dict) else {}

    archetype = _archetype_of(rule_id)
    role_cfg = roles.get(archetype) if isinstance(roles.get(archetype), dict) else {}
    rule_cfg = rules.get(rule_id) if isinstance(rules.get(rule_id), dict) else {}

    if path_override:
        chosen_roots = list(path_override)
    elif "roots" in rule_cfg:
        chosen_roots = _as_str_list(rule_cfg.get("roots"))
    elif "roots" in role_cfg:
        chosen_roots = _as_str_list(role_cfg.get("roots"))
    else:
        chosen_roots = default_roots

    excludes = _dedupe(
        list(_RULE_DEFAULT_EXCLUDES.get(rule_id, ()))
        + default_excludes
        + _as_str_list(role_cfg.get("excludes"))
        + _as_str_list(rule_cfg.get("excludes"))
    )

    resolved = [_resolve_root(repo_root, r) for r in chosen_roots]
    graph_roots = compute_graph_roots(repo_root, rule_id, resolved)

    exempt = False
    exempt_reason = ""
    if rule_id in _TOOLKIT_CLI_EXEMPT_RULES:
        exempt_base = (repo_root / _TOOLKIT_CLI_EXEMPT_RELPATH).resolve()
        kept = [r for r in resolved if not _is_within(r, exempt_base)]
        if not kept and resolved:
            exempt = True
            exempt_reason = (
                f"{rule_id} exempts the toolkit CLI tree "
                f"{_TOOLKIT_CLI_EXEMPT_RELPATH!r} (ATDD's own console output is the product)"
            )
        resolved = kept

    return ScanPolicy(
        scan_roots=[str(r) for r in resolved],
        scan_excludes=excludes,
        exempt=exempt,
        exempt_reason=exempt_reason,
        graph_roots=graph_roots,
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
