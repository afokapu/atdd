# Component: component:author-atdd-substrate:author-issue-body:FeatureBinding:backend:domain
"""The issue↔feature binding primitive (#1635).

One place that answers three questions about a declared feature URN:

* is it shaped like a feature identity at all (``is_feature_urn``)?
* does it resolve to a real feature YAML under ``plan/`` (``resolve_feature``)?
* which WMBTs does that feature declare (``feature_wmbts``)?

BOUNDARY: this lives planner-side deliberately. ``author_publish.publish_issue``
must validate a binding before it writes, and the planner tree may NOT
``import atdd.coach`` (planner.theme.commons-coach-boundary, #970). The coach
resolver and the coach validator both DELEGATE here — the dependency points
coach → planner, never the reverse.

Reading ``plan/`` off disk is the whole point: the lookup this replaces shelled
out to ``gh issue list --label atdd-wmbt``, and #1477 removed the command that
minted those labels with no replacement. Nothing here touches a provider.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

#: ``feature:<wagon>:<name>`` — the only shape that is a feature identity.
#: A train identity (``train:<subject>:<slug>``) deliberately does not match:
#: the #1626 drift was a train URN sitting in the body's Feature row.
_FEATURE_URN_RE = re.compile(r"^feature:[a-z][a-z0-9-]*:[a-z][a-z0-9-]*$")

#: The body's Metadata table row, e.g. ``| Feature | `feature:w:n` |``.
_BODY_FEATURE_RE = re.compile(
    r"(?im)^\s*\|\s*Feature\s*\|\s*`?\s*([^\s|`]+)\s*`?\s*\|"
)

_WMBT_URN_RE = re.compile(r"^wmbt:([a-z][a-z0-9-]*):([DLPCEMYRK][0-9]{3})$")


def is_feature_urn(value: Optional[str]) -> bool:
    """True when ``value`` is shaped like ``feature:<wagon>:<name>``."""
    return bool(value) and bool(_FEATURE_URN_RE.match(value or ""))


def feature_in_body(body: Optional[str]) -> Optional[str]:
    """The Feature value the issue body's Metadata table declares, if any."""
    match = _BODY_FEATURE_RE.search(body or "")
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _slug_to_dir(slug: str) -> str:
    return slug.replace("-", "_")


def plan_root(start: Optional[Path] = None) -> Path:
    """The ``plan/`` directory to resolve against."""
    return (Path(start) if start is not None else Path.cwd()) / "plan"


def plan_is_available(start: Optional[Path] = None) -> bool:
    """True when there is a ``plan/`` tree to resolve against.

    Resolution is only meaningful against a real plan tree. Hermetic callers
    that mint issues in a bare temp directory have nothing to validate, so the
    binding check is skipped rather than failing them for the absence of a
    graph they never had.
    """
    return plan_root(start).is_dir()


@dataclass(frozen=True)
class FeatureBinding:
    """A declared feature URN plus its verdict against ``plan/``."""

    urn: Optional[str]
    resolved: bool
    reason: Optional[str]          # None | "unbound" | "malformed" | "unresolved"
    path: Optional[Path] = None
    wmbts: List[str] = field(default_factory=list)
    detail: str = ""


def resolve_feature(urn: Optional[str], start: Optional[Path] = None) -> FeatureBinding:
    """Resolve a declared feature URN against the ``plan/`` tree under ``start``.

    Never raises: the verdict is the return value, so both the write-side guard
    and the read-side lookup can report rather than explode.
    """
    if not urn:
        return FeatureBinding(
            urn=None, resolved=False, reason="unbound",
            detail="the issue carries no feature binding",
        )

    if not is_feature_urn(urn):
        return FeatureBinding(
            urn=urn, resolved=False, reason="malformed",
            detail=(
                f"{urn!r} is not a feature identity; expected "
                f"feature:<wagon>:<name>"
            ),
        )

    _, wagon, name = urn.split(":")
    path = plan_root(start) / _slug_to_dir(wagon) / "features" / f"{_slug_to_dir(name)}.yaml"
    if not path.is_file():
        return FeatureBinding(
            urn=urn, resolved=False, reason="unresolved",
            detail=f"feature {urn} resolves to nothing in plan/ (expected {path})",
        )

    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return FeatureBinding(
            urn=urn, resolved=False, reason="unresolved",
            detail=f"feature {urn} names an unreadable YAML at {path}: {exc}",
        )

    if str(doc.get("urn") or "").strip() != urn:
        return FeatureBinding(
            urn=urn, resolved=False, reason="unresolved",
            detail=(
                f"feature {urn} resolves to {path}, whose urn: is "
                f"{doc.get('urn')!r} — the path and the identity disagree"
            ),
        )

    wmbts = [str(w).strip() for w in (doc.get("wmbts") or []) if str(w).strip()]
    return FeatureBinding(
        urn=urn, resolved=True, reason=None, path=path, wmbts=wmbts,
        detail=f"feature {urn} resolves to {path}",
    )


def feature_wmbts(urn: Optional[str], start: Optional[Path] = None) -> List[str]:
    """The WMBT URNs a feature declares, or ``[]`` when it does not resolve."""
    return list(resolve_feature(urn, start).wmbts)


def wmbt_paths(wmbts: List[str], start: Optional[Path] = None) -> Dict[str, Path]:
    """Map each WMBT URN to the YAML path its identity implies.

    Derived from the URN rather than probed on disk, so a caller can render a
    location for a WMBT whose file has not been authored yet.
    """
    paths: Dict[str, Path] = {}
    for urn in wmbts:
        match = _WMBT_URN_RE.match(urn or "")
        if not match:
            continue
        wagon, code = match.group(1), match.group(2)
        paths[urn] = plan_root(start) / _slug_to_dir(wagon) / f"{code}.yaml"
    return paths
