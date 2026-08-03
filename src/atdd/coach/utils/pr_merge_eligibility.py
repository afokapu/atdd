# URN: component:govern-lifecycle:enforcement-substrate:pr_merge_eligibility:backend:domain
# Runtime: python
# Purpose: The one representation of which lifecycle phases may carry a PR whose merge auto-closes an ATDD issue.

"""Merge eligibility, stated once (issue #1710).

``coach.pr.merge-blocks-on-pre-smoke-close`` carried its decision twice: a prose
description naming ``atdd:REFACTOR``/``atdd:COMPLETE``, and a ``phase_labels``
table whose ``merge_blocked`` list — mirrored again as a Python frozenset in the
validator — left ``atdd:SMOKE`` merge-eligible. Nothing compared them, so the
strict gate permitted exactly what the rule it binds forbade, from 3.50.0 until
PR #1691 auto-closed #1689 at ``atdd:SMOKE`` and PR #1648 did the same to #1635.

Two things changed here, and the second matters more than the first.

**The set is the allowed one, not the blocked one.** ``merge_blocked`` was the
complement written out by hand, so every phase the machine grew had to be
remembered in it — and ``SMOKE`` was not. Blocked is now *computed* as the
complement of :func:`merge_allowed_phases`, which means an unrecognised phase
blocks by default. A gate whose safety depends on somebody remembering to extend
a list is not a gate; the list was the bug, not the missing entry.

**The enforcement reads it rather than restating it.** The precedent is
``phase_machine.convention.yaml``, whose phase order is walked out of the
authored convention rather than forked, explicitly so no second ordering can
drift. ``phase_labels.merge_allowed`` is read the same way.

What the complement sweeps in is deliberate, not incidental:

* ``atdd:SMOKE`` — the phase this issue is about. ``REFACTOR`` carries
  ``autonomy: operator`` and the terminal hop to ``COMPLETE`` (#1611); closing at
  SMOKE skips precisely the operator sign-off REFACTOR exists to require.
* ``atdd:BLOCKED`` — an escape entered by operator decision from any rung. Its
  lifecycle is suspended *short of* REFACTOR, so a merge that closes it skips the
  same sign-off. It is the pre-SMOKE case wearing a different label.
* ``atdd:OBSOLETE`` — terminal, and reached by an operator transition. Letting a
  merge perform the retirement would hand every author a one-label bypass of a
  rule whose disposition is ``strict``.

Read by ``atdd.coach.validators.test_pr_merge_blocks_pre_smoke_close``; the
human-facing restatements are held to this same table by
``test_e071_unit_004_restatements_agree_with_the_table``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Tuple

import yaml

import atdd

#: The convention that declares the table. Resolved against the installed
#: package, not the working tree, so a consumer repo reads the shipped
#: conventions rather than looking for a ``src/atdd/`` it does not have.
CONVENTION_PATH = (
    Path(atdd.__file__).resolve().parent / "coach" / "conventions" / "pr.convention.yaml"
)

#: Prefix GitHub issue labels carry, e.g. ``atdd:REFACTOR``.
PHASE_LABEL_PREFIX = "atdd:"

_cache: Dict[Path, Tuple[str, ...]] = {}


class MergeEligibilityUnreadableError(RuntimeError):
    """The table could not be read.

    Raised rather than defaulted. A strict gate that silently falls back to some
    built-in set is a gate with a second source of truth again — and a
    default-open one would reopen this very defect.
    """


def merge_allowed_phases(convention_path: Optional[Path] = None) -> Tuple[str, ...]:
    """The phases a merge may auto-close from, in the order the convention authors them.

    Order is preserved (not sorted) because :func:`render_allowed_phrase` reads
    it back to an operator, and lifecycle order is how an operator thinks.
    """
    path = Path(convention_path) if convention_path is not None else CONVENTION_PATH
    cached = _cache.get(path)
    if cached is not None:
        return cached

    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise MergeEligibilityUnreadableError(
            f"cannot read merge eligibility from {path}: {exc}"
        ) from exc

    table = document.get("phase_labels")
    allowed = (table or {}).get("merge_allowed") if isinstance(table, dict) else None
    if not isinstance(allowed, list) or not allowed:
        raise MergeEligibilityUnreadableError(
            f"{path} declares no phase_labels.merge_allowed list; that table is the "
            "only statement of which phases may carry an auto-closing PR"
        )

    phases = tuple(str(phase).strip().upper() for phase in allowed)
    _cache[path] = phases
    return phases


def is_merge_blocked(
    phase: Optional[str], *, allowed: Optional[Sequence[str]] = None
) -> bool:
    """True when an auto-closing PR must not merge against an issue at ``phase``.

    The complement of :func:`merge_allowed_phases`, computed — so a phase the
    convention has never heard of blocks. Accepts the bare phase (``"SMOKE"``) or
    the label form (``"atdd:SMOKE"``).
    """
    if not phase:
        # No phase resolved means no evidence the lifecycle was satisfied. The
        # scan drops such resolutions before this point; answering "blocked" here
        # keeps the seam fail-closed for any other caller.
        return True

    normalized = str(phase).strip()
    if normalized.lower().startswith(PHASE_LABEL_PREFIX):
        normalized = normalized[len(PHASE_LABEL_PREFIX):]
    normalized = normalized.upper()

    eligible = tuple(allowed) if allowed is not None else merge_allowed_phases()
    return normalized not in {str(p).strip().upper() for p in eligible}


def render_allowed_phrase(allowed: Optional[Iterable[str]] = None) -> str:
    """The merge-eligible phases as an operator reads them: ``atdd:X or atdd:Y``.

    Every human-facing restatement of this decision must contain this exact
    string, which is what makes prose-vs-table drift a test failure instead of an
    incident (E071-UNIT-004).
    """
    labels = [
        f"{PHASE_LABEL_PREFIX}{str(p).strip().upper()}"
        for p in (allowed if allowed is not None else merge_allowed_phases())
    ]
    if not labels:
        raise MergeEligibilityUnreadableError("no merge-eligible phase to render")
    if len(labels) == 1:
        return labels[0]
    return f"{', '.join(labels[:-1])} or {labels[-1]}"
