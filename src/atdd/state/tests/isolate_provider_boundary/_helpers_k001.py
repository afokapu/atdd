# URN: component:isolate-provider-boundary:test-support:mirror_repo:backend:tests
# Runtime: python
# Purpose: Build a real git repo on a real bare remote carrying one real, legally-evidenced, committed projection object — the branch a mirror runs against and the merge-authority gate judges.

"""A real branch for the mirror to run against (#1400 K001).

The K001 acceptances are about what happens to a **mergeable branch** when a provider is attached
to it, so the branch has to be genuinely mergeable: a real object in a real store, projected to
real canonical bytes, committed with the trailers the ∅->INIT gate actually demands, on a real
clone of a real bare remote. A fixture that hand-wrote a YAML file would be asking merge authority
to judge something no workflow could have produced, and a "the gate still passes" result would
mean nothing.

Built by driving the conformance suite's own steps, so the branch these acceptances judge is the
same branch C002 proves the workflow produces — not a second, parallel idea of one.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

from atdd.state import conformance


def bare_repo_with_object(root: Path) -> Tuple[Path, str, str]:
    """``(repo, uid, base_ref)`` — a clone of a bare remote with one committed projection object.

    ``base_ref`` is the commit before the object landed, so a merge-authority run over
    ``base..HEAD`` sees exactly the change the object's commit made — which is what CI sees on a
    pull request.
    """
    context = conformance.setup(Path(root))
    base = conformance.git(context.author, "rev-parse", "HEAD")

    for step in (conformance.step_mint, conformance.step_project, conformance.step_commit):
        step(context)

    return context.author, context.uid, base
