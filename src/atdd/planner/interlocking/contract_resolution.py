# URN: component:plan:train-interlocking:ContractResolution:backend:application
# Runtime: python
# Purpose: Resolve a message payload's contract identity to a schema body ($id) and
#          to the authored contracts registry (#1314 items C + E).
"""Payload-contract resolution for the interlocking sanity checks.

Two questions, both asked of a declared ``payload.contract`` identity:

  * **body** — does some ``*.schema.{json,yaml,yml}`` under a ``contracts/``
    directory *declare* this identity as its ``$id``? (#1314 item C)
  * **registry** — is the identity a member of the authored
    ``contracts/_contracts.yaml`` registry? (#1314 item E)

Split out of :mod:`.sanity` so that module stays a readable list of rule checks;
these are its private collaborators, not part of the sanity rule surface.

Stdlib + yaml only; no other-layer imports (boundaries §3.3).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

_log = logging.getLogger(__name__)

_CONTRACT_ID_PREFIX = "contract:"
_SCHEMA_SUFFIXES = (".schema.json", ".schema.yaml", ".schema.yml")
CONTRACT_REGISTRY_PATH = "contracts/_contracts.yaml"


def normalize_identity(identity: str) -> str:
    """Strip an optional leading ``contract:`` so a bare contract identity and the
    ``contract:``-prefixed ``$id`` form set by ``create_contract`` (#1330) compare
    equal — this resolver works either side of the #1330 boundary."""
    identity = (identity or "").strip()
    if identity.startswith(_CONTRACT_ID_PREFIX):
        identity = identity[len(_CONTRACT_ID_PREFIX):]
    return identity


def _convention_schema_path(contract: str) -> str:
    """The deterministic contract-file location for an identity, per
    ``planner.artifact-naming.contract-file-mapping``: colons and variant dots
    become directory separators —
    ``theme:seg:aspect.variant → contracts/theme/seg/aspect/variant.schema.json``.
    """
    ident = normalize_identity(contract)
    parts = ident.replace(":", "/").replace(".", "/")
    return f"contracts/{parts}.schema.json"


def _schema_declared_id(path: Path) -> "str | None":
    """Read a schema body's declared ``$id`` (``None`` if unreadable or absent)."""
    try:
        text = path.read_text(encoding="utf-8")
        doc = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        # An unreadable / unparseable schema body simply does not declare a
        # resolvable $id; the payload-contract-body rule reports it as unresolved.
        _log.debug(
            "schema $id read skipped (unreadable contract body)",
            extra={
                "path": str(path),
                "error": str(exc).splitlines()[0][:120],
            },
        )
        return None
    if isinstance(doc, dict):
        sid = doc.get("$id")
        return sid if isinstance(sid, str) else None
    return None


def _iter_contract_schemas(root: Path):
    """Yield every contract schema body under any ``contracts/`` directory."""
    seen: "set[Path]" = set()
    for suffix in _SCHEMA_SUFFIXES:
        for path in root.glob(f"**/contracts/**/*{suffix}"):
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path


def contract_resolves(contract: str, root: Path) -> "tuple[bool, str]":
    """Resolve a payload contract *identity* to a schema body by ``$id``, not by a
    filename glob (#1314 item C).

    A contract ``a:b:c`` resolves iff some ``*.schema.{json,yaml,yml}`` under a
    ``contracts/`` directory declares a ``$id`` equal to the identity — normalizing
    an optional ``contract:`` prefix on either side (#1330). The deterministic
    convention path (where ``create_contract`` writes) is checked first; otherwise
    every contract body is scanned, so a correctly-identified but
    non-canonically-named file still resolves (kills the #244 leaf-mismatch false
    negative). A body whose ``$id`` differs never satisfies the identity (kills the
    old leaf-glob false positive). Returns
    ``(resolved, expected_convention_path)``.
    """
    target = normalize_identity(contract)
    convention_path = _convention_schema_path(contract)

    # 1. Deterministic convention path — the location `create_contract` writes to.
    candidate = root / convention_path
    if candidate.is_file() and \
            normalize_identity(_schema_declared_id(candidate) or "") == target:
        return True, convention_path

    # 2. $id scan — resolves a correctly-identified body at a non-canonical path.
    for path in _iter_contract_schemas(root):
        if normalize_identity(_schema_declared_id(path) or "") == target:
            return True, str(path.relative_to(root))

    return False, convention_path


def _entry_identity(entry) -> "str | None":
    """The identity an entry declares, under any of the accepted spellings."""
    if not isinstance(entry, dict):
        return None
    ident = entry.get("identity") or entry.get("id") or entry.get("$id")
    return str(ident) if ident else None


def _registry_identities(contracts) -> "set[str]":
    """Normalized identities from a ``contracts:`` block — a list of entries, or a
    mapping keyed by identity whose entry may restate (or omit) it."""
    identities: "set[str]" = set()
    if isinstance(contracts, list):
        for entry in contracts:
            ident = _entry_identity(entry)
            if ident:
                identities.add(normalize_identity(ident))
    elif isinstance(contracts, dict):
        for key, entry in contracts.items():
            identities.add(normalize_identity(_entry_identity(entry) or str(key)))
    return identities


def load_contract_registry(root: Path) -> "set[str]":
    """Return the set of registered contract identities from the authored
    ``contracts/_contracts.yaml`` registry (normalized: ``contract:`` stripped).

    The registry is the single source of truth for
    ``identity -> {path, theme, producers, consumers}``, authored by
    ``create_contract`` (#1330) and validated for coherence by #1332. Accepts
    either a list of entries under ``contracts:`` or a mapping keyed by identity
    (matching #1332's ``load_registry``). A missing or unparseable registry
    yields the empty set, so a declared ``payload.contract`` then fails closed
    (unregistered) rather than crashing. Stdlib + yaml only.
    """
    reg = root / CONTRACT_REGISTRY_PATH
    if not reg.is_file():
        return set()
    try:
        doc = yaml.safe_load(reg.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        # A malformed registry is owned by the #1332 coherence validator, not
        # this rule; treat as empty so we fail closed instead of raising.
        _log.debug(
            "contract registry read skipped (unparseable)",
            extra={
                "path": str(reg),
                "error": str(exc).splitlines()[0][:120],
            },
        )
        return set()
    contracts = doc.get("contracts") if isinstance(doc, dict) else None
    return _registry_identities(contracts)
