# URN: component:define-plans:criteria:planner_node_path_references:backend:tests
# Runtime: python
# Purpose: No active planner node may send an author to the plan/_lego/ catalogue, which never existed (#1971).

"""The dead `plan/_lego/` catalogue is named by nothing (issue #1971).

`planner.acceptance.authoring-guidelines` instructed authors to take a
`metric_id` from ``plan/_lego/acceptance-metrics.yaml``. That file never existed:
``git log --all --diff-filter=A`` over every path containing ``lego`` returns
nothing, so it was never created rather than deleted, and the whole
``plan/_lego/`` directory is absent.

It survived because the convention decomposition preserved fragments verbatim
(``extraction_mode: high_fidelity``, ``source_fragments_preserved: true``).
Faithful extraction cannot notice that a fragment describes a file nobody made.

Same class as the ``templates/CONDUCTOR.md`` pointer removed in #1940: a live
reference, in a node marked ``status: active``, to something not on disk — which
a reader cannot distinguish from an instruction still in force.

The catalogue's job, "here are the metric ids you may bind to", is now done by
``planner.criteria.metric-mapping``, bound to a validator by #1958. So the repair
is to name that node, never to create ``plan/_lego/``.

Deliberately narrow. An earlier draft scanned every repo-shaped path in every
active planner node and reported nine — but seven were path TEMPLATES in prose
(``contracts/theme/seg1/seg2/aspect/variant.schema.json``,
``contracts/commons/WRONG/uuid.schema.json``) which are illustrations, not
claims. A guard that cannot tell a template from a claim reports noise, and
noise is how a real finding gets ignored. This pins the one dead catalogue and
nothing else; the general problem needs a way to mark a path as illustrative
first.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root


pytestmark = [pytest.mark.platform]

#: The catalogue that never existed. Retired by #1971.
_DEAD_CATALOGUE = "plan/_lego/"


def _planner_nodes(root: Path):
    d = root / "src" / "atdd" / "planner" / "conventions" / "nodes"
    return sorted(d.rglob("*.convention.yaml")) if d.is_dir() else []


def test_the_dead_lego_catalogue_is_absent_from_the_tree() -> None:
    """Guard the premise: if someone creates it, this test's reasoning changes."""
    assert not (find_repo_root() / "plan" / "_lego").exists(), (
        "plan/_lego/ now exists. #1971 removed references to it on the grounds "
        "that it never had — revisit that decision rather than deleting this."
    )


def test_no_planner_node_sends_an_author_to_the_dead_catalogue() -> None:
    """No convention node may name `plan/_lego/` in any form."""
    root = find_repo_root()
    offenders = [
        str(n.relative_to(root))
        for n in _planner_nodes(root)
        if _DEAD_CATALOGUE in n.read_text(encoding="utf-8")
    ]
    assert offenders == [], (
        "a planner node names the plan/_lego/ catalogue, which has never "
        "existed — bind metric ids through planner.criteria.metric-mapping "
        "instead (#1971):\n  " + "\n  ".join(offenders)
    )
