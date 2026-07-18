"""Discovery of a real composition-root-wired four-tier feature in the toolkit.

Three gates in this package assert against a *real* four-tier DDD feature living
under the toolkit scan root — not against the purpose-built fixtures in
``coder/validators/fixtures/`` (``test_wagon_boundaries_toolkit_root_config_driven``
explicitly requires those to be excluded from discovery).

Until the coach's sub-worker orchestration was pruned, the sole such feature was
``consolidate_coach_workspace/enforce_surface_conformance`` (#865), and the gates
hardcoded that path. It was pruned with its wagon, and no surviving feature in
core carries a composition root, so a hardcoded path would simply point at
nothing.

Rather than delete the assertions or pin a weaker stand-in, the gates now
*discover* their subject and skip when it is absent. The skip is keyed strictly
on **absence of the subject** — no four-tier feature exists to scan — and never
on the identity of the repo. The day a composition-root-wired four-tier feature
reappears in core, these gates reactivate on their own with no edit required.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

# A four-tier feature is a composition root plus the three wired tiers beneath
# ``src/``. ``integration/`` is deliberately not required: it is present in some
# features and absent in others, and its absence does not make a feature
# non-four-tier.
_REQUIRED_TIERS = ("domain", "application", "presentation")


def _is_four_tier_feature(candidate: Path) -> bool:
    """True when ``candidate`` is a composition-root-wired four-tier feature."""
    if not (candidate / "composition.py").is_file():
        return False
    src = candidate / "src"
    return all((src / tier).is_dir() for tier in _REQUIRED_TIERS)


def find_four_tier_feature(discovery_root: Path) -> Optional[Path]:
    """Return a real four-tier feature under ``discovery_root``, or ``None``.

    ``discovery_root`` is the directory whose immediate children are wagons, so
    features sit at ``<discovery_root>/<wagon>/<feature>``. Results are sorted so
    the choice is deterministic across runs and machines.
    """
    if not discovery_root.is_dir():
        return None
    for wagon in sorted(p for p in discovery_root.iterdir() if p.is_dir()):
        for feature in sorted(p for p in wagon.iterdir() if p.is_dir()):
            if _is_four_tier_feature(feature):
                return feature
    return None


#: Reason string shared by all three gates, so the dormancy is greppable and the
#: lost coverage is visible in pytest output rather than silently absorbed.
NO_FOUR_TIER_FEATURE = (
    "no composition-root-wired four-tier feature exists under the toolkit scan "
    "root; the #865 exemplar (consolidate_coach_workspace/"
    "enforce_surface_conformance) was pruned with the coach sub-worker "
    "orchestration. This gate reactivates automatically when such a feature "
    "reappears in core."
)


__all__ = ["NO_FOUR_TIER_FEATURE", "find_four_tier_feature"]
