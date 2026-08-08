"""Shared harness for the #1590 issue↔train binding tests.

Every helper builds a REAL State Store on a tmp path and a REAL ``plan/`` tree on
disk. The acceptances are about what actually lands in ``objects.data.train`` and
what actually resolves out of a repository's own registry, so neither is mocked.

THE FIXTURE REPO IS DELIBERATELY NOT ATDD. Its wagon is ``freight-yard``, its
train subjects are ``rolling-stock`` and ``yard-ops``, and none of its train ids
appears anywhere in atdd's ``plan/_trains.yaml``. That is the point: a check that
resolves only because it runs inside atdd is the defect, not the evidence. The
same fixture also carries NO ``.atdd/config.yaml`` layout override of any kind —
the trap ``interlocking_layout`` already is, pointing the runtime-interlocking
detector at atdd's own ``src/atdd/runtime/interlocking/*.py`` paths.

An atdd train id is exported as :data:`ATDD_TRAIN_ID` purely so a test can assert
it does NOT resolve in the fixture repo.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import yaml

from atdd.state.store import StateStore

from ._issue_binding_store import (
    GITHUB_PROVIDER, ISSUE_REF_KIND, WORK_ITEM_KIND, control_root, link_issue,
    open_store, read_issue_data,
)

# ---------------------------------------------------------------------------
# The consumer repository's OWN vocabulary — nothing atdd would ever declare
# ---------------------------------------------------------------------------
CONSUMER_WAGON = "freight-yard"
CONSUMER_TRAIN = "train:rolling-stock:couple-wagons"
CONSUMER_TRAIN_LEGACY = "0042-couple-wagons"
CONSUMER_TRAIN_UNROUTED = "train:yard-ops:shunt-empties"
CONSUMER_INTERLOCKING = "interlocking:couple-and-depart"

#: Well-formed, and registered by nobody.
ABSENT_TRAIN = "train:rolling-stock:no-such-train"

#: Not a train identity at all — the shape 11 live work items actually carry.
PLACEHOLDER_TRAIN = "TBD"

#: A REAL atdd train id, exported only to assert it does NOT resolve in the
#: consumer fixture. If it ever did, atdd's registry had leaked into the lookup.
ATDD_TRAIN_ID = "train:self-compliance:validate-lifecycle"

#: The feature the seeded work items bind to, so the feature-binding guard on the
#: create path is satisfied and only the TRAIN guard is under test.
CONSUMER_FEATURE = f"feature:{CONSUMER_WAGON}:couple-wagons"


def _wagon_dir(wagon: str) -> str:
    return wagon.replace("-", "_")


def write_consumer_plan_tree(
    root: Path,
    *,
    trains: Iterable[str] = (CONSUMER_TRAIN, CONSUMER_TRAIN_UNROUTED),
    aliases: Optional[Dict[str, str]] = None,
    routed: Iterable[str] = (CONSUMER_TRAIN,),
    route_by_path: bool = True,
    with_interlocking: bool = True,
) -> Path:
    """A real ``plan/`` tree for a repository that is NOT atdd.

    Writes the registry index, the per-train manifests, the alias map, one
    feature (so the create path's feature guard is satisfiable), and — unless
    ``with_interlocking`` is False — one interlocking artifact plus its index,
    routing through ``routed``.

    ``route_by_path`` selects how the route names its train: by ``train_path``
    (the default) or by ``train_id``. Both spellings must count as coverage, so
    both are exercised.
    """
    plan = root / "plan"
    trains = list(trains)

    registry: Dict[str, Any] = {"trains": {}}
    for train_id in trains:
        subject, slug = train_id[len("train:"):].split(":", 1)
        relpath = f"plan/_trains/{subject}/{slug}.yaml"
        bucket = registry["trains"].setdefault(subject, {}).setdefault("nominal", [])
        bucket.append({
            "train_id": train_id,
            "description": f"{slug} in the {subject} subject",
            "path": relpath,
            "wagons": [CONSUMER_WAGON],
        })
        manifest = root / relpath
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(yaml.safe_dump({
            "train_id": train_id,
            "title": slug,
            "description": f"{slug} in the {subject} subject",
            "themes": ["commons"],
            "participants": [f"wagon:{CONSUMER_WAGON}"],
        }, sort_keys=False), encoding="utf-8")

    plan.mkdir(parents=True, exist_ok=True)
    (plan / "_trains.yaml").write_text(
        yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
    )

    alias_map = {CONSUMER_TRAIN_LEGACY: CONSUMER_TRAIN} if aliases is None else aliases
    (plan / "_trains").mkdir(parents=True, exist_ok=True)
    (plan / "_trains" / "_aliases.yaml").write_text(
        yaml.safe_dump({
            "version": "1.0",
            "name": f"{CONSUMER_WAGON} train alias map",
            "aliases": {
                legacy: canonical[len("train:"):].replace(":", "/")
                for legacy, canonical in alias_map.items()
            },
        }, sort_keys=False),
        encoding="utf-8",
    )

    features = plan / _wagon_dir(CONSUMER_WAGON) / "features"
    features.mkdir(parents=True, exist_ok=True)
    (features / "couple_wagons.yaml").write_text(yaml.safe_dump({
        "urn": CONSUMER_FEATURE,
        "wagon": f"wagon:{CONSUMER_WAGON}",
        "description": "The consumer repo's own feature.",
        "sizing": {"wmbts": 1, "footprint_score": 1, "footprint_size": "XS"},
        "wmbts": [f"wmbt:{CONSUMER_WAGON}:C001"],
        "components": {"backend": {"application": [
            {"type": "use_cases", "count": 1, "rationale": "the consumer's own use case"},
        ]}},
    }, sort_keys=False), encoding="utf-8")

    if with_interlocking:
        write_consumer_interlocking(root, routed=routed, route_by_path=route_by_path)
    return plan


def write_consumer_interlocking(
    root: Path,
    *,
    routed: Iterable[str] = (CONSUMER_TRAIN,),
    route_by_path: bool = True,
    interlocking_id: str = CONSUMER_INTERLOCKING,
) -> Path:
    """One interlocking artifact under the canonical home, plus its index entry."""
    slug = interlocking_id.split(":", 1)[-1]
    home = root / "plan" / "_trains" / "_interlockings"
    home.mkdir(parents=True, exist_ok=True)

    routes = []
    for train_id in routed:
        subject, train_slug = train_id[len("train:"):].split(":", 1)
        route: Dict[str, Any] = {"route_id": f"{train_slug}-nominal"}
        if route_by_path:
            route["train_path"] = f"plan/_trains/{subject}/{train_slug}.yaml"
        else:
            route["train_id"] = train_id
        routes.append(route)

    path = home / f"{slug}.yaml"
    path.write_text(yaml.safe_dump({
        "schema_version": "1.0.0",
        "interlocking_id": interlocking_id,
        "title": slug,
        "theme": "commons",
        "status": "draft",
        "source": {"path": f"plan/_trains/_interlockings/{slug}.yaml",
                   "content_digest": "fixture"},
        "lifelines": [{"ref": f"wagon:{CONSUMER_WAGON}"}],
        "routes": routes,
    }, sort_keys=False), encoding="utf-8")

    (root / "plan" / "_trains" / "_interlockings.yaml").write_text(yaml.safe_dump({
        "version": "1.0",
        "interlockings": [{
            "interlocking_id": interlocking_id,
            "path": f"plan/_trains/_interlockings/{slug}.yaml",
            "theme": "commons",
            "status": "draft",
        }],
    }, sort_keys=False), encoding="utf-8")
    return path


def issue_record(number: int, train: Optional[str], *, status: str = "PLANNED") -> Dict[str, Any]:
    """One scan input record: the shape the store rows are flattened into."""
    return {"number": number, "status": status, "train": train}


def seed_issue(
    store: StateStore,
    *,
    slug: str,
    issue_number: int,
    state: str = "PLANNED",
    train: Optional[str] = None,
    body: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """A work item linked to its github issue, as the real mint leaves it.

    ``feature`` is always populated so the create path's #1635 feature guard is
    satisfied and only the TRAIN guard is ever what a refusal is attributable to.
    """
    data: Dict[str, Any] = {
        "title": slug,
        "type": "implementation",
        "branch": f"feat/{slug}",
        "train": train,
        "feature": CONSUMER_FEATURE,
        "body": body,
    }
    data.update(extra or {})
    return link_issue(
        store, slug=slug, issue_number=issue_number, state=state, data=data,
    )


def rule_ids(violations) -> list:
    """The rule ids a scan reported, in order."""
    return [v.rule_id for v in violations]
