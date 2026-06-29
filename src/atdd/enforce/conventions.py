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
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import yaml

_log = logging.getLogger(__name__)

# Rules that exempt the toolkit's own CLI source tree. Mirrors the legacy
# in-core ``coder.logging.print`` exemption of ``src/atdd`` (V4 / scan_policy
# docstring of the cw prototype): ATDD's own ``print``s are product output.
_TOOLKIT_CLI_EXEMPT_RULES = frozenset({"coder.logging.print"})
_TOOLKIT_CLI_EXEMPT_RELPATH = "src/atdd"


@dataclass(frozen=True)
class RuleMetadata:
    rule_id: str
    severity: Optional[int]
    disposition: str  # strict | suppress-and-clean | advisory


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
    disp = meta.get("disposition") or "strict"
    return RuleMetadata(
        rule_id=rule_id,
        severity=int(sev) if isinstance(sev, int) else None,
        disposition=str(disp),
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
        default_excludes
        + _as_str_list(role_cfg.get("excludes"))
        + _as_str_list(rule_cfg.get("excludes"))
    )

    resolved = [_resolve_root(repo_root, r) for r in chosen_roots]

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
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
