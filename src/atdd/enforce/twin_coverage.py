# URN: component:govern-registry:core-twin-coverage:backend:domain
# Runtime: python
# Purpose: Measure the CORE-to-EXTENSION direction of the rule relation — whether a
#          core coder/tester obligation exists anywhere but core — so a carve-out
#          cannot report success while the obligation it moved has disappeared.
"""Core twin coverage (#1714 / wmbt:govern-registry:E003).

This wagon already governs two directions of the core/extension rule relation:
:func:`~atdd.enforce.registry.find_mirror_incoherences` resolves every extension
node's ``source.legacy_rule_id`` against the live core registry (extension → core),
and :func:`~atdd.enforce.registry.assert_core_precedes_extension` raises on any
rule_id declared in both. The third direction — **core → extension** — is what this
module adds: given a core rule, does the obligation exist anywhere else?

It matters because :func:`~atdd.enforce.registry.evaluate_core_deletion` opens with
``if not node_twins: continue``. A **twinless** core rule is precisely the one whose
obligation exists in core and nowhere else, so deleting it is maximal loss — and it
is the case the succession guard waves through. Coverage is what closes that: once
every core rule is either mirrored or adjudicated, the twinless branch cannot fire.

A rule is COVERED two ways, and they are reported apart on purpose:

* :data:`COVERED_BY_TWIN` — an extension node declares it as its ``legacy_rule_id``.
  The obligation exists outside core; moving the declaration relocates it.
* :data:`COVERED_BY_RECORD` — the classification record carries a why-not verdict
  (``ATDD-INTERNAL`` / ``SUBSTRATE-SPEC``). The obligation was adjudicated never to
  move, with quoted evidence.

Collapsing the two would let an unexamined rule pass as settled: "covered" would no
longer distinguish *moved* from *deliberately not moved*.

Distinct from :mod:`atdd.enforce.coverage_report`, which answers a different
question — which extension rules CI actually ENFORCES versus merely reports. This
module says nothing about enforcement; it says whether the obligation is declared
anywhere but core.

**Both readers are load-bearing, and both have a wrong twin that silently passes.**

* Provenance is read off the node DOCUMENT, via
  :func:`~atdd.enforce.registry.iter_extension_nodes`. It must NOT be read from the
  flat single-node rule projection: :func:`~atdd.coach.utils.rule_binding.single_node_rule_dict`
  maps a node onto the shape monolith ``rules:[]`` consumers expect and keeps ten
  keys, of which ``source`` is not one. Provenance keyed off that projection reads as
  absent on every node, not present on the ones that have it.
* The core surface is walked by :func:`~atdd.coach.utils.rule_binding.extract_rules`,
  which recurses into nested ``rules:`` lists. A depth-1 read cannot see
  ``canonical_rules.rules[]`` in ``coder/conventions/logging.convention.yaml`` — the
  omission that understated the corpus in #1969.

Both are pinned by E003-UNIT-002 and E003-UNIT-003 so a future reader cannot
reintroduce either quietly.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from atdd.coach.utils.rule_binding import extract_rules
from atdd.enforce.registry import iter_extension_nodes

_log = logging.getLogger(__name__)

__all__ = [
    "CLASSIFICATION_RECORD",
    "COVERED_BY_RECORD",
    "COVERED_BY_TWIN",
    "CoreRule",
    "RuleCoverage",
    "TwinCoverage",
    "core_coder_tester_surface",
    "live_twin_coverage",
    "measure_twin_coverage",
    "twins_by_core_rule",
    "why_not_verdicts",
]

#: How a core rule came to be covered. Kept apart so a report can distinguish an
#: obligation that MOVED from one adjudicated never to move.
COVERED_BY_TWIN = "twin"
COVERED_BY_RECORD = "record"

#: The classification record's declared home, relative to the repo root.
CLASSIFICATION_RECORD = Path("docs/1714-agnostic-mirror-coverage.md")

#: The archetypes whose convention surface this measures.
_ARCHETYPES = ("coder", "tester")

#: A why-not verdict from the SHARED METHOD: the rule states an obligation on ATDD's
#: own substrate, not on consumer code, so no agnostic mirror is owed for it.
_WHY_NOT_VERDICTS = ("ATDD-INTERNAL", "SUBSTRATE-SPEC")

#: A verdict row names its rule in a leading backtick cell and carries a recognised
#: verdict in the next one. The TOKEN is what makes the row a verdict: a leading
#: rule-shaped cell alone also matches the family-assignment and incoherence tables,
#: which record work still to do rather than obligations discharged.
_WHY_NOT_ROW = re.compile(
    r"^\|\s*`((?:coder|tester)\.[a-z0-9.\-]+)`\s*\|\s*("
    + "|".join(_WHY_NOT_VERDICTS)
    + r")\s*\|"
)


@dataclass(frozen=True)
class CoreRule:
    """One core coder/tester declaration, with where and how it is declared.

    ``kind`` is ``"node"`` for an atomized ``nodes/`` declaration and ``"monolith"``
    otherwise. It is carried because a monolith rule cannot hold per-rule provenance,
    so its mirror waits on the core-side atomization (#1218) rather than being
    authorable today.
    """

    rule_id: str
    kind: str
    disposition: str
    source_path: str


@dataclass(frozen=True)
class RuleCoverage:
    """A core rule and what covers it. ``twins`` is empty for a record-covered rule."""

    rule_id: str
    covered_by: str
    twins: tuple[str, ...]


@dataclass(frozen=True)
class TwinCoverage:
    """An exact partition of the measured core surface into covered and uncovered.

    Every rule in :attr:`core_surface` appears in exactly one of :attr:`covered` and
    :attr:`uncovered`. Counting a rule twice would understate the shortfall, which is
    the one error this measure exists to avoid.
    """

    core_surface: tuple[str, ...]
    covered: tuple[RuleCoverage, ...]
    uncovered: tuple[str, ...]

    @property
    def move_ready(self) -> bool:
        """Whether every core obligation exists outside core or was adjudicated.

        False while any rule is neither, because moving one then destroys it rather
        than relocating it.
        """
        return not self.uncovered


def _convention_files(conventions: Path) -> list[Path]:
    """Every convention file under *conventions*, caches excluded."""
    if not conventions.is_dir():
        return []
    return [p for p in sorted(conventions.rglob("*.convention.yaml")) if "__pycache__" not in p.parts]


def _declared_rules(path: Path, root: Path, conventions: Path):
    """Yield ``(rule_id, CoreRule)`` for every rule *path* declares.

    Walked by :func:`extract_rules`, so a rule nested inside a monolith is yielded
    like any other — a depth-1 read would silently shrink the surface.
    """
    kind = "node" if "nodes" in path.relative_to(conventions).parts else "monolith"
    for file_path, _yaml_path, rule in extract_rules(path):
        rule_id = rule.get("id")
        if isinstance(rule_id, str):
            yield rule_id, CoreRule(
                rule_id=rule_id,
                kind=kind,
                disposition=str(rule.get("disposition") or "unset"),
                source_path=str(file_path.relative_to(root)),
            )


def core_coder_tester_surface(repo_root: str | Path) -> dict[str, CoreRule]:
    """Every coder/tester rule declared under ``src/atdd/{coder,tester}/conventions``."""
    root = Path(repo_root)
    surface: dict[str, CoreRule] = {}
    for archetype in _ARCHETYPES:
        conventions = root / "src" / "atdd" / archetype / "conventions"
        for path in _convention_files(conventions):
            surface.update(_declared_rules(path, root, conventions))
    return surface


def twins_by_core_rule(substrate_home: str | Path) -> dict[str, tuple[str, ...]]:
    """Core rule_id -> the extension nodes declaring it as their ``legacy_rule_id``.

    Read off the node document. See the module docstring on why the flat single-node
    rule projection cannot be used here.
    """
    twins: dict[str, list[str]] = {}
    for node in iter_extension_nodes(substrate_home):
        if node.legacy_rule_id:
            twins.setdefault(node.legacy_rule_id, []).append(node.rule_id)
    return {core_id: tuple(sorted(mirrors)) for core_id, mirrors in twins.items()}


def why_not_verdicts(record_path: str | Path) -> frozenset[str]:
    """Rule_ids carrying a why-not verdict row in the classification record.

    An absent or unreadable record yields the empty set: nothing is adjudicated, so
    nothing is covered by it, and every twinless rule stays in the shortfall. That is
    the safe direction — treating an unreadable record as full coverage would report a
    shortfall of zero — but an unreadable one is still a fault, so it is logged with
    its path rather than passed over in silence.
    """
    path = Path(record_path)
    if not path.is_file():
        return frozenset()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _log.warning(
            "unreadable classification record — no rule is covered by a verdict",
            extra={"record_path": str(path), "error": str(exc)},
        )
        return frozenset()
    return frozenset(
        match.group(1)
        for line in text.splitlines()
        if (match := _WHY_NOT_ROW.match(line.strip()))
    )


def measure_twin_coverage(
    core_ids: Iterable[str],
    *,
    twins: Mapping[str, tuple[str, ...]],
    why_not: Iterable[str],
) -> TwinCoverage:
    """Partition *core_ids* into covered and uncovered. Pure; both sources injected.

    A twin takes precedence over a verdict: an obligation that demonstrably exists
    outside core is stronger evidence than an adjudication that it need not.
    """
    surface = tuple(sorted(set(core_ids)))
    adjudicated = frozenset(why_not)
    covered: list[RuleCoverage] = []
    uncovered: list[str] = []

    for rule_id in surface:
        mirrors = tuple(twins.get(rule_id) or ())
        if mirrors:
            covered.append(RuleCoverage(rule_id, COVERED_BY_TWIN, mirrors))
        elif rule_id in adjudicated:
            covered.append(RuleCoverage(rule_id, COVERED_BY_RECORD, ()))
        else:
            uncovered.append(rule_id)

    return TwinCoverage(
        core_surface=surface,
        covered=tuple(covered),
        uncovered=tuple(uncovered),
    )


def live_twin_coverage(
    repo_root: str | Path,
    record_path: str | Path | None = None,
) -> TwinCoverage:
    """Measure twin coverage over the real core trees, extension nodes and record."""
    root = Path(repo_root)
    record = Path(record_path) if record_path is not None else root / CLASSIFICATION_RECORD
    return measure_twin_coverage(
        core_coder_tester_surface(root),
        twins=twins_by_core_rule(root),
        why_not=why_not_verdicts(record),
    )
