"""Store-as-source-of-truth gate: the provider must be a mirror, not the source (#1503).

The Store holds the truth and GitHub projects it. Nothing enforced that, so
provider-origin issues drifted the other way: the work_item became a bodyless
shell whose prose lived only on GitHub.

This module is the packaged implementation the ``pre-push`` hook dispatches to
(the ``atdd.version_check._gate_main`` pattern, #1492): the installed hook is a
dispatcher, never a snapshot copy, so a fix here propagates on upgrade.

Scope is deliberately narrow — **the work_item bound to the branch being
pushed**, not the repo. A repo-wide blocking gate would red-gate every branch on
430 rows of pre-existing history (see #1516, which backfills them). Repo-wide
drift is still *reported*, as an advisory count, so the debt stays visible
without holding anyone's push hostage.

Binding is resolved through ``external_refs``, never through the ``data`` blob.
Store-authored rows carry no issue number in ``data`` at all, so a reader keyed
on ``data.issue_number`` misclassifies every one of them — the exact mistake
that produced a wrong shell census while investigating #1503.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger(__name__)

#: Exit codes the hook honours: 0 allows the push, 1 blocks it.
EXIT_ALLOW = 0
EXIT_BLOCK = 1


@dataclass
class GateResult:
    """Outcome of one gate evaluation.

    ``blocking`` failures stop the push; ``advisory`` lines are reported and
    never do. Keeping them in separate fields is what makes the scoped-blocking
    /repo-wide-advisory split testable rather than a matter of print formatting.
    """

    blocking: List[str] = field(default_factory=list)
    advisory: List[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return bool(self.blocking)

    @property
    def exit_code(self) -> int:
        return EXIT_BLOCK if self.blocked else EXIT_ALLOW


def _work_item_for_branch(conn, branch: str) -> Optional[Tuple[str, Dict[str, Any], Optional[str]]]:
    """Return ``(uid, data, state)`` for the work_item bound to ``branch``.

    The branch lives in the ``data`` blob (it is not a provider identifier, so
    it has no ``external_refs`` row); binding to an *issue* is what goes through
    ``external_refs``. Returns None when the branch owns no work_item — that is
    the branch-registration gate's concern, not this one's.
    """
    row = conn.execute(
        "SELECT uid, data, state FROM objects "
        "WHERE kind='work_item' AND json_extract(data, '$.branch')=?",
        (branch,),
    ).fetchone()
    if row is None:
        return None
    uid, raw, state = row[0], row[1], row[2]
    try:
        data = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        data = {}
    return uid, data, state


def _issue_number_for(conn, uid: str) -> Optional[str]:
    """The GitHub issue bound to ``uid`` via ``external_refs`` (the authority)."""
    row = conn.execute(
        "SELECT ref_value FROM external_refs "
        "WHERE object_uid=? AND provider='github' AND ref_kind='issue'",
        (uid,),
    ).fetchone()
    return row[0] if row else None


def _has_body(data: Dict[str, Any]) -> bool:
    """True when the work_item carries real prose, not an empty placeholder."""
    return bool(str(data.get("body") or "").strip())


def _title_disagreement(data: Dict[str, Any]) -> Optional[str]:
    """The stored-title/body-H1 disagreement for ``data``, or None (#1654).

    Delegates to ``atdd.state.issue_title`` rather than re-deriving the H1: that
    module is the ONE fence-aware extractor, shared with the two title-writing
    paths. A second parser here that disagreed with theirs would recreate, in
    the checker itself, the one-fact-two-representations defect it exists to
    catch.
    """
    from atdd.state.issue_title import title_violations

    found = title_violations(data.get("title"), str(data.get("body") or ""))
    return found[0] if found else None


def repo_wide_title_drift(conn) -> Tuple[int, int]:
    """Return ``(disagreeing, with_h1)`` across the whole Store.

    Only rows whose body actually declares an H1 are in the denominator. A body
    with no H1 has not stated a title to disagree with, and 619 of the 822 rows
    are in that state legitimately — counting them as failures would drown the
    real signal (24) in noise nobody can act on.

    Evaluated in Python rather than SQL because the H1 read is fence-aware, and
    a ``json_extract`` + ``LIKE`` would be exactly the naive scan that reported
    105 false disagreements against this same corpus.
    """
    disagreeing = 0
    with_h1 = 0
    from atdd.state.issue_title import extract_issue_title

    for raw in conn.execute(
        "SELECT data FROM objects WHERE kind='work_item'"
    ).fetchall():
        try:
            data = json.loads(raw[0]) if raw[0] else {}
        except (TypeError, ValueError):
            continue
        if extract_issue_title(str(data.get("body") or "")) is None:
            continue
        with_h1 += 1
        if _title_disagreement(data):
            disagreeing += 1
    return disagreeing, with_h1


def repo_wide_drift(conn) -> Tuple[int, int]:
    """Return ``(bodyless_bound, total_bound)`` across the whole Store.

    Counts only rows bound to a GitHub issue through ``external_refs``: an
    unbound row is a different defect (#1516) and would inflate this number
    with rows no backfill can reach.
    """
    row = conn.execute(
        """
        SELECT
          SUM(CASE WHEN COALESCE(TRIM(json_extract(o.data, '$.body')), '') = ''
                   THEN 1 ELSE 0 END),
          COUNT(*)
        FROM objects o
        JOIN external_refs e
          ON e.object_uid = o.uid AND e.provider='github' AND e.ref_kind='issue'
        WHERE o.kind='work_item'
        """
    ).fetchone()
    return int(row[0] or 0), int(row[1] or 0)


def _gh_issue_json(issue_number: str) -> Optional[Dict[str, Any]]:
    """``gh issue view --json labels`` as a dict, or None when it cannot be read.

    Every None path is logged with its reason: a silently-skipped provider read
    is indistinguishable from agreement, which is how a gate becomes a stub.
    """
    try:
        proc = subprocess.run(
            ["gh", "issue", "view", str(issue_number), "--json", "labels"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _log.warning(
            "gh unavailable; label check skipped",
            extra={"issue": issue_number, "error": str(exc)},
        )
        return None

    if proc.returncode != 0:
        _log.warning(
            "gh issue view failed; label check skipped",
            extra={
                "issue": issue_number,
                "rc": proc.returncode,
                "stderr": proc.stderr.strip(),
            },
        )
        return None

    try:
        return json.loads(proc.stdout)
    except ValueError as exc:
        _log.warning(
            "gh returned unparseable JSON; label check skipped",
            extra={"issue": issue_number, "error": str(exc)},
        )
        return None


def _github_labels(issue_number: str) -> Optional[List[str]]:
    """Labels on ``issue_number``, or None when GitHub cannot be reached.

    None means *unknown*, never *empty* — conflating the two would let an
    offline push silently pass a divergence check it never actually ran.
    """
    payload = _gh_issue_json(issue_number)
    if payload is None:
        return None
    return [lbl.get("name", "") for lbl in payload.get("labels", [])]


def _phase_from_labels(labels: List[str]) -> Optional[str]:
    """The ``atdd:<PHASE>`` label's phase, or None when the issue carries none."""
    for name in labels:
        if name.startswith("atdd:"):
            return name.split(":", 1)[1]
    return None


def evaluate(conn, branch: str, *, check_provider: bool = True) -> GateResult:
    """Evaluate the gate for ``branch`` against the Store behind ``conn``."""
    result = GateResult()

    bodyless, total = repo_wide_drift(conn)
    if bodyless:
        result.advisory.append(
            f"repo-wide drift: {bodyless}/{total} issue-bound work_items are bodyless "
            f"(advisory — see #1516 for the backfill)"
        )

    disagreeing, with_h1 = repo_wide_title_drift(conn)
    if disagreeing:
        result.advisory.append(
            f"repo-wide title drift: {disagreeing}/{with_h1} work_items with an H1 "
            f"carry a title that disagrees with it (advisory — pre-existing "
            f"history; see #1654)"
        )

    found = _work_item_for_branch(conn, branch)
    if found is None:
        result.advisory.append(
            f"no work_item is bound to branch {branch!r}; content gate not applicable"
        )
        return result

    uid, data, state = found
    issue = _issue_number_for(conn, uid)

    # Blocking check 1 — purely local, so it is deterministic and offline-safe.
    if not _has_body(data):
        result.blocking.append(
            f"work_item {uid!r} (branch {branch}) has no body in the Store.\n"
            f"  GitHub is not a mirror here — it is the source, which inverts the model.\n"
            f"  Fix: atdd author issue --revise {issue or '<issue>'} --body-file <path>"
        )

    # Blocking check 2 — also purely local (#1654). Scoped to THIS branch's work
    # item for the same reason check 1 is: 24 rows of pre-existing history must
    # not red-gate every push in the repo. Scoped, it asks only that the work
    # item you are pushing agrees with itself.
    disagreement = _title_disagreement(data)
    if disagreement:
        result.blocking.append(
            f"work_item {uid!r} (branch {branch}) {disagreement}.\n"
            f"  The stored title and the body's H1 are two representations of one\n"
            f"  fact; a source of truth that contradicts itself is not one.\n"
            f"  Fix: atdd author issue --revise {issue or '<issue>'} "
            f"--body-file <path>  (the title follows the body's H1)"
        )

    # Blocking check 3 — needs the provider, so it is skipped (loudly) offline.
    if check_provider and issue:
        _check_divergence(result, issue, state)

    return result


def _check_divergence(result: GateResult, issue: str, state: Optional[str]) -> None:
    """Compare the Store phase against GitHub's ``atdd:`` label for ``issue``.

    Appends to ``result`` in place. An unreadable provider is advisory, never a
    silent pass — see :func:`_gh_issue_json`.
    """
    labels = _github_labels(issue)
    if labels is None:
        result.advisory.append(
            f"could not read GitHub labels for #{issue}; divergence check skipped"
        )
        return

    if not state:
        return

    remote_phase = _phase_from_labels(labels)
    if remote_phase is None:
        result.blocking.append(
            f"Store/GitHub divergence on #{issue}: Store says {state}, "
            f"GitHub carries no atdd: label at all.\n"
            f"  Fix: atdd coach sync-labels {issue}  (per-issue — never --all)"
        )
    elif remote_phase != state:
        result.blocking.append(
            f"Store/GitHub divergence on #{issue}: Store says {state}, "
            f"GitHub label says {remote_phase}.\n"
            f"  Fix: atdd coach transition {issue} {state}  (per-issue, additive)"
        )


def render(result: GateResult) -> List[str]:
    """Operator-facing lines for ``result``, most-severe last.

    Shared by the pre-push hook and ``atdd coach store-gate`` so the two cannot
    drift into reporting the same Store differently — the failure mode this
    whole issue is about.
    """
    lines = [f"ATDD store-mirror gate: {line}" for line in result.advisory]
    if result.blocked:
        lines.append("\nATDD: the Store is not the source of truth here.\n")
        lines.extend(f"  {line}\n" for line in result.blocking)
    return lines


class StoreUnavailable(RuntimeError):
    """The State Store could not be opened.

    Raised rather than handled in place so each caller decides its own policy:
    the pre-push hook allows the push (a missing Store is not this gate's
    failure), while the CLI reports a usage error. Previously only the hook
    guarded this, so the CLI died with a traceback on the same condition.
    """


def current_branch() -> str:
    """The checked-out branch, or ``"HEAD"`` when detached."""
    proc = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    )
    return proc.stdout.strip()


def evaluate_branch(branch: str, *, check_provider: bool = True) -> GateResult:
    """Open the Store and evaluate ``branch`` against it.

    The single seam both entry points share, so the hook and
    ``atdd coach store-gate`` can never diverge in how they resolve the Store.
    """
    from atdd.state.db import connect, init_state_store

    try:
        conn = connect(init_state_store())
    except Exception as exc:  # noqa: BLE001 — surfaced as StoreUnavailable
        raise StoreUnavailable(str(exc)) from exc
    return evaluate(conn, branch, check_provider=check_provider)


def _gate_main() -> None:
    """Hook entry point. Exit 0 allows the push, exit 1 blocks it.

    Mirrors ``atdd.version_check._gate_main`` so the pre-push hook stays a
    dispatcher over the packaged implementation.
    """
    branch = current_branch()
    if not branch or branch == "HEAD":
        # Detached HEAD: no branch to resolve a work_item from. Not this gate's
        # failure mode, and blocking here would strand a rebase.
        sys.exit(EXIT_ALLOW)

    try:
        result = evaluate_branch(
            branch, check_provider=os.environ.get("CI") != "true"
        )
    except StoreUnavailable as exc:
        print(
            f"ATDD store-mirror gate: cannot open the State Store ({exc}); skipped.",
            file=sys.stderr,
        )
        sys.exit(EXIT_ALLOW)

    if result.blocked:
        print("\nATDD: Pre-push blocked.", file=sys.stderr)
    for line in render(result):
        print(line, file=sys.stderr)

    sys.exit(result.exit_code)


if __name__ == "__main__":
    _gate_main()
