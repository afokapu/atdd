"""What a committed evidence artifact's PATH has to look like to count as one (#1945).

Split out of :mod:`atdd.state.evidence` for the reason ``smoke_evidence`` was (#1951):
that module is the §6 evidence model — the policy table and the legal-transition
validator — and this is a question about filenames. They met only because
``evidence_for`` needs an answer to it.

The split is also what keeps the dependency acyclic. Nothing here imports ``evidence``:
the gate vocabulary is *derived from* the policy, so the policy is passed in rather than
reached for. :func:`gate_artifact_names` takes the transition table it should read, and
:func:`is_gate_evidence_artifact` takes the names that came back.

Why any of it exists: ``evidence_for`` used to test ``path.startswith('.atdd/evidence/')``
and nothing else, so every committed file under that directory minted
``smoke_evidence_artifact`` — the sole requirement of BOTH ``GREEN->SMOKE`` and
``SMOKE->REFACTOR``. A ``README.md`` there was a walk out of SMOKE, and the directory
could never be used for any other committed evidence without forging smoke evidence.
"""
from __future__ import annotations

from typing import Any, FrozenSet, Iterable, Mapping, Sequence, Set, Tuple

#: Prefix of the committed merge-authority evidence artifact. It must stay equal to
#: ``merge_driver.EVIDENCE_RELATIVE``, which is the module that OWNS the path; it is
#: restated rather than imported to keep the derivation's hot path free of the driver,
#: and ``test_evidence_token_derivation_paths.py`` is the tie that stops the two
#: literals from drifting apart.
MERGE_EVIDENCE_PREFIX = ".atdd/evidence/"

#: The separators a gate filename may join two phase names with. Both spellings are live
#: in-tree (``PLANNED-RED.yaml``, ``GREEN->SMOKE.yaml``); no phase name contains a ``-``.
GATE_SEPARATORS: Tuple[str, ...] = ("->", "-")


def gate_artifact_names(
    transitions: Iterable[Mapping[str, Any]],
    ladder: Sequence[str],
) -> FrozenSet[str]:
    """Every filename stem that NAMES a gate in ``transitions``.

    Derived, not typed out, so a rung added to the §6 table becomes an admissible
    filename by that edit alone; a second list would drift, and the drift would reach an
    operator as "the evidence is missing" rather than "the filename is unknown". It has
    already earned that: #1947 added the BLOCKED and OBSOLETE escapes as wildcard entries
    and the vocabulary grew from 27 names to 55 with no edit here.

    One branch per entry shape: a concrete ``from``; a wildcard, which has no ``from`` key
    and names one gate per rung (the escapes, and ``* -> TOMBSTONED``); and the mint, whose
    ``from`` is ``None``, named by its target phase alone. Absent and present-and-``None``
    are different claims, hence the membership test.
    """
    names: Set[str] = set()
    for entry in transitions:
        to_phase = str(entry["to"])
        if "from" not in entry:
            sources: Tuple[str, ...] = tuple(ladder)
        elif entry["from"] is None:
            names.add(to_phase)
            continue
        else:
            sources = (str(entry["from"]),)
        names.update(
            f"{source}{sep}{to_phase}" for source in sources for sep in GATE_SEPARATORS
        )
    return frozenset(names)


def is_gate_evidence_artifact(path: str, uid: str, gate_names: FrozenSet[str]) -> bool:
    """Is ``path`` the COMMITTED gate-evidence artifact of the object ``uid``?

    Only the two shapes ``govern_cli._evidence_at`` — the reader that OWNS the artifact —
    looks for: ``.atdd/evidence/<uid>/<gate>.yaml``, the per-gate shard, and
    ``.atdd/evidence/<uid>.yaml``, the flat form. Committed is the requirement, not an
    accident: evidence a merge cannot see is evidence the merge does not have (§6).
    Anything else under the prefix merely lives in the directory and attests to nothing.

    ``uid`` is load-bearing: the derivation sees every path in the commit once per object
    in it, so an unscoped test let one object's honest artifact evidence every other
    object advancing beside it.

    NOT to be "aligned" with ``.atdd/smoke-evidence/<N>.yaml``, a near-miss of the name and
    a different artifact entirely: the #358 ratchet's local, gitignored, operator-TYPED
    stamp, written by ``atdd validate coder --smoke-required`` without running a test.
    Pointing this at it would either never fire (a gitignored path is never a changed path)
    or, if that ignore lifted, mint the token from a typed stamp — a brand-new false green.
    #1602 closed that class; ``test_evidence_token_derivation_paths.py`` keeps it closed.

    Shape, not content (#1945 decision 1): whether the file parses as a token list is the
    artifact's own schema to say, and the merge authority reads changed paths.
    """
    if not uid or not path.startswith(MERGE_EVIDENCE_PREFIX):
        return False
    segments = path[len(MERGE_EVIDENCE_PREFIX):].split("/")
    if len(segments) == 1:
        return segments[0] == f"{uid}.yaml"
    if len(segments) != 2 or segments[0] != uid:
        return False
    stem, _, extension = segments[1].rpartition(".")
    return extension == "yaml" and stem in gate_names
