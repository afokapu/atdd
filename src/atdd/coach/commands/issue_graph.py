# URN: component:integration-hardening:coach-single-command-driver:E003:application
# Runtime: python
# Purpose: Build a per-issue architecture context section (wagon + train + sibling WMBTs)
#          for pre-injection into the spawn launch prompt.
"""Issue architecture context builder for coach spawn prompt enrichment.

Implements ``atdd repo graph --issue <N> --format prompt``:

1. Reads .atdd/manifest.yaml to resolve issue N → wagon slug.
2. Reads plan/<wagon>/_<wagon>.yaml for wagon name/description/features.
3. Reads plan/<wagon>/*.yaml (excluding _<wagon>.yaml) for sibling WMBT URNs.
4. Reads plan/_trains.yaml to find the wagon's position in its train.
5. Returns a ``## Architecture context`` markdown section, or None when
   the issue has no wagon (graceful degrade — no exception raised).

The return value is identical to what the spawn pipeline splices into
.launch_prompt.txt, ensuring the CLI surface and the spawn path are
not duplicating the graph-walk logic.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def _load_yaml(path: Path) -> dict:
    """Load a YAML file, returning an empty dict on any failure."""
    try:
        import yaml

        return yaml.safe_load(path.read_text()) or {}
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return {}


def _store_wagon(issue_number: int, repo_root: Path) -> Optional[str]:
    """Wagon for *issue_number* from the State Store, or None on any miss."""
    try:
        from atdd.state.work_item_reader import WorkItemReader

        with WorkItemReader(control_root=repo_root) as reader:
            return reader.wagon(issue_number)
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return None


def _store_train(issue_number: int, repo_root: Path) -> Optional[str]:
    """Train for *issue_number* from the State Store, or None on any miss."""
    try:
        from atdd.state.work_item_reader import WorkItemReader

        with WorkItemReader(control_root=repo_root) as reader:
            return reader.train(issue_number)
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return None


def _wagon_slug_for_issue(issue_number: int, repo_root: Path) -> Optional[str]:
    """Return the wagon slug for *issue_number*.

    #1270 slice D: read the wagon from the State Store only (authoritative since
    #1203); the ``.atdd/manifest.yaml`` fallback is retired.
    """
    from_store = _store_wagon(issue_number, repo_root)
    return str(from_store) if from_store else None


def _read_wagon_meta(wagon_slug: str, repo_root: Path) -> dict:
    """Read the wagon manifest YAML (_<wagon>.yaml) and return its data."""
    wagon_dir = repo_root / "plan" / wagon_slug.replace("-", "_")
    wagon_yaml = wagon_dir / f"_{wagon_slug.replace('-', '_')}.yaml"
    if not wagon_yaml.is_file():
        return {}
    return _load_yaml(wagon_yaml)


def _read_sibling_wmbts(wagon_slug: str, repo_root: Path) -> list[str]:
    """Return sorted list of WMBT URNs from the wagon directory."""
    wagon_dir = repo_root / "plan" / wagon_slug.replace("-", "_")
    if not wagon_dir.is_dir():
        return []
    prefix = f"_{wagon_slug.replace('-', '_')}"
    urns: list[str] = []
    for path in sorted(wagon_dir.glob("*.yaml")):
        if path.stem.startswith(prefix) or path.parent.name == "features":
            continue
        data = _load_yaml(path)
        urn = data.get("urn", "")
        if urn.startswith("wmbt:"):
            urns.append(urn)
    return urns


def _train_wagon_order(train_id: str, repo_root: Path) -> list[str]:
    """Return the ordered wagon list for *train_id* from plan/_trains.yaml."""
    trains_yaml = repo_root / "plan" / "_trains.yaml"
    if not trains_yaml.is_file():
        return []
    data = _load_yaml(trains_yaml)
    for _group, sections in data.get("trains", {}).items():
        for _section_name, entries in sections.items():
            for entry in entries:
                if entry.get("train_id") == train_id:
                    return list(entry.get("wagons") or [])
    return []


def build_architecture_context_for_wagon(
    wagon_slug: str,
    *,
    train_id: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> Optional[str]:
    """Build the ``## Architecture context`` markdown section for *wagon_slug*.

    Does NOT consult ``.atdd/manifest.yaml`` — callers pass the wagon slug
    (and optionally train_id) directly. Returns ``None`` when the wagon
    directory doesn't exist under ``plan/`` (graceful degrade — caller
    decides what fallback text to splice).

    Used by ``atdd issue <slug>`` at issue-creation time (#682): the manifest
    entry doesn't exist yet at that point, so the wagon-by-issue lookup that
    ``build_issue_architecture_context`` performs is unavailable.

    Args:
        wagon_slug: Wagon slug (e.g. ``govern-lifecycle``).
        train_id: Optional train ID to enrich the rendered context.
        repo_root: Repo root (default: auto-detected via find_repo_root()).

    Returns:
        Markdown string (starting with ``## Architecture context``) or None
        when the wagon manifest cannot be located.
    """
    if repo_root is None:
        from atdd.coach.utils.repo import find_repo_root

        repo_root = find_repo_root()

    wagon_meta = _read_wagon_meta(wagon_slug, repo_root)
    if not wagon_meta:
        return None

    wagon_name = wagon_meta.get("name") or wagon_slug
    wagon_desc = wagon_meta.get("description") or ""
    wagon_urn = wagon_meta.get("urn") or f"wagon:{wagon_slug}"
    features = wagon_meta.get("features") or []

    wagon_order = _train_wagon_order(train_id, repo_root) if train_id else []
    sibling_wmbts = _read_sibling_wmbts(wagon_slug, repo_root)

    lines: list[str] = [
        "## Architecture context",
        "",
        f"**Wagon:** `{wagon_urn}` — {wagon_name}",
    ]
    if wagon_desc:
        lines.append(f"> {wagon_desc}")
    lines.append("")

    if train_id:
        lines.append(f"**Train:** `{train_id}`")
        if wagon_order:
            position = (wagon_order.index(wagon_slug) + 1) if wagon_slug in wagon_order else None
            order_str = " → ".join(wagon_order)
            pos_note = f" (position {position}/{len(wagon_order)})" if position else ""
            lines.append(f"**Wagon order:** {order_str}{pos_note}")
        lines.append("")

    if features:
        lines.append("**Features:**")
        for feat in features:
            feat_urn = feat.get("urn") if isinstance(feat, dict) else str(feat)
            lines.append(f"- `{feat_urn}`")
        lines.append("")

    if sibling_wmbts:
        lines.append("**Sibling WMBTs in this wagon:**")
        for urn in sibling_wmbts:
            lines.append(f"- `{urn}`")
        lines.append("")

    return "\n".join(lines)


def _read_sibling_wagons_from_trains(wagon_slug: str, repo_root: Path) -> list[str]:
    """Return other wagon slugs sharing a train with *wagon_slug*."""
    trains_yaml = repo_root / "plan" / "_trains.yaml"
    if not trains_yaml.is_file():
        return []
    data = _load_yaml(trains_yaml)
    siblings: list[str] = []
    for _group, sections in data.get("trains", {}).items():
        for _section_name, entries in sections.items():
            for entry in entries:
                wagons = list(entry.get("wagons") or [])
                if wagon_slug in wagons:
                    siblings.extend(w for w in wagons if w != wagon_slug)
    return siblings


def build_wagon_launch_prompt(
    wagon_slug: str,
    *,
    repo_root: Optional[Path] = None,
) -> Optional[str]:
    """Build a compact wagon-scoped launch-prompt section (≤ 2 KB).

    Reads the wagon manifest and WMBT files to emit a ``## Wagon Architecture``
    markdown block containing wagon identity, features, WMBT IDs, contracts,
    and train-siblings. Designed to be injected into the spawn launch prompt
    before the agent starts work so structural context is available from the
    first message.

    Returns ``None`` when *wagon_slug* has no manifest (graceful degrade —
    no exception raised). The caller decides what fallback text to splice.

    Args:
        wagon_slug: Wagon slug (e.g. ``spawn-agents``).
        repo_root: Repo root (default: auto-detected via find_repo_root()).

    Returns:
        Markdown string starting with ``## Wagon Architecture``, or None.
    """
    if repo_root is None or not (repo_root / "plan").is_dir():
        from atdd.coach.utils.repo import find_repo_root

        repo_root = find_repo_root()

    wagon_meta = _read_wagon_meta(wagon_slug, repo_root)
    if not wagon_meta:
        return None

    wagon_name = wagon_meta.get("name") or wagon_slug
    wagon_urn = wagon_meta.get("urn") or f"wagon:{wagon_slug}"
    wagon_desc = wagon_meta.get("description") or ""
    features = wagon_meta.get("features") or []
    produce = wagon_meta.get("produce") or []
    consume = wagon_meta.get("consume") or []

    sibling_wmbts = _read_sibling_wmbts(wagon_slug, repo_root)
    sibling_wagons = _read_sibling_wagons_from_trains(wagon_slug, repo_root)

    lines: list[str] = [
        "## Wagon Architecture",
        "",
        f"**Wagon:** `{wagon_urn}` — {wagon_name}",
    ]
    # Truncate description to 60 chars to keep under 2 KB budget.
    if wagon_desc:
        desc_text = wagon_desc[:60].rstrip()
        if len(wagon_desc) > 60:
            desc_text += "…"
        lines.append(f"> {desc_text}")
    lines.append("")

    # Features — use the slug (last segment of URN) for compactness.
    if features:
        feat_slugs: list[str] = []
        for feat in features:
            feat_urn = feat.get("urn") if isinstance(feat, dict) else str(feat)
            feat_slugs.append(feat_urn.split(":")[-1] if feat_urn else str(feat))
        lines.append(f"**Features ({len(feat_slugs)}):** {', '.join(feat_slugs)}")
        lines.append("")

    # WMBT IDs — last segment of the URN (e.g. "E001").
    if sibling_wmbts:
        wmbt_ids: list[str] = []
        for urn in sibling_wmbts:
            parts = urn.split(":")
            wmbt_ids.append(parts[-1] if len(parts) >= 3 else urn)
        lines.append(f"**WMBTs ({len(wmbt_ids)}):** {', '.join(wmbt_ids)}")
        lines.append("")

    # Contracts — produce then consume. Use the last colon-segment of each name
    # to stay compact (e.g. "coach:spawn:atdd-spawn-cli" → "atdd-spawn-cli").
    def _contract_slug(raw: str) -> str:
        return raw.split(":")[-1] if ":" in raw else raw

    produce_names = [
        _contract_slug(p.get("name") if isinstance(p, dict) else str(p))
        for p in produce
        if p
    ]
    consume_names = [
        _contract_slug(c.get("name") if isinstance(c, dict) else str(c))
        for c in consume
        if c
    ]
    if produce_names:
        lines.append(f"**Produce ({len(produce_names)}):** {', '.join(produce_names)}")
    if consume_names:
        lines.append(f"**Consume ({len(consume_names)}):** {', '.join(consume_names)}")
    if produce_names or consume_names:
        lines.append("")

    # Siblings in train — cap at 6 to stay within 2 KB budget.
    if sibling_wagons:
        _MAX_SIBLINGS = 6
        shown = sibling_wagons[:_MAX_SIBLINGS]
        remainder = len(sibling_wagons) - _MAX_SIBLINGS
        sib_str = ", ".join(shown)
        if remainder > 0:
            sib_str += f" +{remainder} more"
        lines.append(f"**Siblings:** {sib_str}")
        lines.append("")

    return "\n".join(lines)


def build_issue_architecture_context(
    issue_number: int,
    *,
    repo_root: Optional[Path] = None,
) -> Optional[str]:
    """Build the ``## Architecture context`` markdown section for *issue_number*.

    Resolves the issue → wagon mapping via ``.atdd/manifest.yaml``, then
    delegates to :func:`build_architecture_context_for_wagon`. Returns
    ``None`` when the issue has no wagon assigned (graceful degrade).

    Args:
        issue_number: GitHub issue number to look up.
        repo_root: Repo root (default: auto-detected via find_repo_root()).

    Returns:
        Markdown string or None.
    """
    if repo_root is None:
        from atdd.coach.utils.repo import find_repo_root

        repo_root = find_repo_root()

    wagon_slug = _wagon_slug_for_issue(issue_number, repo_root)
    if not wagon_slug:
        return None

    # #1270 slice D: train from the State Store only (authoritative since #1203).
    train_id: Optional[str] = _store_train(issue_number, repo_root)

    return build_architecture_context_for_wagon(
        wagon_slug, train_id=train_id, repo_root=repo_root,
    )
