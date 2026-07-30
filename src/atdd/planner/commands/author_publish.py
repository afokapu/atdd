# Component: component:author-atdd-substrate:author-issue-body:AuthorIssuePublish:backend:application
"""`atdd author issue` store-first publish (#1272).

Planner-side. Turns `atdd author issue` from a body-only authoring tool into a
real create path: after producing the schema-valid body, publish store-first by
default — write the work_item into the State Store (authoritative), then project
onto GitHub and link the single external_ref (#1220).

BOUNDARY: planner-side; imports ``atdd.state`` + ``atdd.integrations.github``
ONLY — it MUST NOT import ``atdd.coach``. The store-first create logic is SHARED
with coach ``atdd issue`` through ``atdd.state.work_item_writer.create_work_item``
(both call the foundational helper; neither archetype imports the other).

Ordering (store-first, #1203/#1272):

1. The store is written authoritatively. If it cannot be reached, FAIL LOUD —
   never degrade to a body-only string (the exact gap that orphaned #1271).
2. GitHub is a projection: create the issue synchronously and link its number as
   the single external_ref. If the projection cannot complete, enqueue the
   outbox (durable retry) and warn — the store work_item still stands (no
   orphan, no store-unaware issue).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_GITHUB_PROVIDER = "github"
_CREATE_ISSUE_OP = "create_issue"
_UPDATE_ISSUE_OP = "update_issue"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class PublishError(Exception):
    """The store-first publish could not complete its AUTHORITATIVE step.

    Raised only when the State Store cannot be reached/written. A failed GitHub
    projection is NOT a PublishError (it is deferred to the outbox); only a store
    failure is, because emitting a body-only result would recreate the #1271
    orphan gap.
    """


@dataclass(frozen=True)
class PublishResult:
    """Outcome of a store-first publish (the store write always succeeded)."""

    slug: str
    state: Optional[str]
    github_number: Optional[int]      # set when the sync projection succeeded
    projection_deferred: bool         # True when enqueued to the outbox instead


@dataclass(frozen=True)
class RevisionResult:
    """Outcome of a store-first issue revision."""

    issue_number: int
    slug: str
    state: Optional[str]
    projection_deferred: bool


def derive_slug(title: str) -> str:
    """Kebab-case slug from a title (the work_item uid when --slug is absent)."""
    return _SLUG_RE.sub("-", (title or "").strip().lower()).strip("-") or "untitled"


def _github_labels(status: str) -> List[str]:
    """The labels the projected GitHub issue carries (parity with `atdd issue`)."""
    return ["atdd-issue", f"atdd:{status}"]


def _require_resolvable_feature(
    feature: Optional[str], control_root: Optional[Path]
) -> None:
    """Refuse a feature URN that does not resolve against ``plan/`` (#1635).

    Skipped when there is no ``plan/`` tree to resolve against: a hermetic caller
    minting into a bare temp directory has no graph to check, and failing it for
    the absence of one it never had would be a guard misfiring rather than
    working. Where a plan tree exists, the binding must be real.
    """
    from atdd.planner.commands.feature_binding import plan_is_available, resolve_feature

    if not plan_is_available(control_root):
        return
    verdict = resolve_feature(feature, control_root)
    if not verdict.resolved:
        raise PublishError(f"invalid --feature: {verdict.detail}")


def _derive_feature(body: str, control_root: Optional[Path]) -> Optional[str]:
    """The feature URN implied by the body's Metadata table, when it resolves.

    Derivation is deliberately narrow: the body's ``Feature`` row is the only
    declaration an author has already made, so it is the only thing there is to
    derive FROM. Anything that does not resolve is not silently accepted — the
    caller refuses instead, which is what makes the null binding unreachable.
    """
    from atdd.planner.commands.feature_binding import feature_in_body, resolve_feature

    declared = feature_in_body(body)
    if declared is None:
        return None
    return declared if resolve_feature(declared, control_root).resolved else None


def publish_issue(
    slug: str,
    body: str,
    *,
    title: str,
    status: str = "INIT",
    issue_type: str = "implementation",
    branch: Optional[str] = None,
    train: Optional[str] = None,
    feature: Optional[str] = None,
    control_root: Optional[Path] = None,
) -> PublishResult:
    """Publish an authored issue store-first; project onto GitHub (outbox on fail).

    Store is authoritative and mandatory: a store failure raises
    :class:`PublishError` (fail loud, never body-only). The GitHub issue is
    created synchronously and its number linked as the one-per-issue external_ref
    (#1220); if that projection fails it is enqueued to the outbox for a durable
    retry while the work_item still stands.
    """
    from atdd.state import provenance
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore
    from atdd.state.work_item_writer import create_work_item
    from atdd.planner.commands.feature_binding import plan_is_available

    # DERIVE-OR-REQUIRE (#1635). Validated BEFORE the store connection is opened,
    # so a refused binding mints nothing at all — no half-published record.
    if plan_is_available(control_root):
        if feature is None:
            feature = _derive_feature(body, control_root)
        if feature is None:
            raise PublishError(
                "no --feature: an issue must declare a feature URN that resolves "
                "in plan/, and none could be derived from the body's Feature row"
            )
        _require_resolvable_feature(feature, control_root)

    data: Dict[str, Any] = {
        "title": title, "type": issue_type, "branch": branch,
        "train": train, "feature": feature, "body": body,
    }

    # 1) STORE-FIRST authoritative write. Fail loud if the store is unreachable.
    try:
        db_path = init_state_store(start=control_root)
        conn = connect(db_path)
    except Exception as exc:
        raise PublishError(
            "State Store unreachable — refusing to author without publishing "
            f"(no body-only degrade; #1271): {exc}"
        ) from exc

    github_number: Optional[int] = None
    projection_deferred = False
    try:
        try:
            create_work_item(conn, slug, state=status, data=data)
        except Exception as exc:
            raise PublishError(
                f"State Store write failed for work_item {slug!r} "
                f"(no body-only degrade; #1271): {exc}"
            ) from exc

        store = StateStore(conn)

        # Provenance stamp (#1557). The store write above is the ONE chokepoint
        # every sanctioned issue-create passes through, so this is where the
        # sanctioned authoring event is appended — first event on the object,
        # which is exactly what the L2 detector checks.
        #
        # NOT wrapped in a try/except, unlike the creator capture below: the
        # stamp is not telemetry. A work item minted without it is precisely the
        # unprovenanced record the invariant exists to catch, so silently
        # swallowing the failure would manufacture the violation it is meant to
        # prevent. A store that cannot append is a store failure — fail loud.
        try:
            provenance.record_authored(store, slug, command="atdd author issue")
        except Exception as exc:
            raise PublishError(
                f"provenance stamp failed for work_item {slug!r} — refusing to mint "
                f"an unprovenanced record (#1557): {exc}"
            ) from exc

        # Creator capture (#1540). The mint is a mandatory chokepoint, so this
        # is where the creating agent session is recorded — read from ambient
        # environment, never asked of the agent. Placed before every return so
        # it covers the deferred-projection and re-author paths too.
        #
        # Wrapped: the operator's intent is the ISSUE. An unrecorded creator is
        # a missing nice-to-have; a failed mint is a broken command. Resolved
        # through the module so the recorder stays substitutable under test.
        try:
            from atdd.state import agent_session as _agent_session

            _agent_session.record_creator(store, slug)
        except Exception as exc:  # never fail the mint over telemetry
            logger.warning(
                "agent session capture failed; the mint stands",
                extra={"slug": slug, "error": str(exc)},
            )

        # Idempotent re-author: if this work_item already carries a github issue
        # ref, it is ALREADY published — reuse that number and NEVER create a
        # second GitHub issue (a duplicate is precisely the #1271 failure this
        # closes). The re-link is a no-op on the one-per-issue unique key (#1220).
        existing = [
            r for r in store.external_refs.for_object(slug)
            if r.provider == _GITHUB_PROVIDER and r.ref_kind == "issue"
        ]
        if existing:
            github_number = int(existing[0].ref_value)
            create_work_item(
                conn, slug, state=status, data=data, github_number=github_number,
            )
            return PublishResult(
                slug=slug, state=status, github_number=github_number,
                projection_deferred=False,
            )

        # 2) GitHub projection (store-first). Sync-create; on a CREATE failure
        # the outbox carries a durable retry. A create success followed by a
        # ref-link failure is handled separately — we must NOT re-enqueue a
        # create (that would duplicate the just-created issue).
        try:
            from atdd.integrations.github.issue_state import create_issue

            github_number = create_issue(
                title=title, body=body, labels=_github_labels(status),
            )
        except Exception as exc:  # the GitHub issue was NOT created — retry it
            projection_deferred = True
            store.sync.enqueue_outbox(
                _GITHUB_PROVIDER, _CREATE_ISSUE_OP,
                {"slug": slug, "title": title, "body": body,
                 "labels": _github_labels(status), "status": status,
                 "type": issue_type},
            )
            logger.warning(
                "github issue create deferred to outbox; store work_item stands",
                extra={"slug": slug, "error": str(exc)},
            )
        else:
            # Issue created — link its number as the single external_ref. A link
            # failure here leaves a created issue that just isn't yet linked; it
            # is reconciled out-of-band. Re-enqueuing a create would duplicate it.
            try:
                create_work_item(
                    conn, slug, state=status, data=data,
                    github_number=github_number,
                )
            except Exception as exc:
                logger.warning(
                    "github issue #%s created but external_ref link failed; "
                    "reconcile out-of-band (not re-created)",
                    github_number, extra={"slug": slug, "error": str(exc)},
                )
    finally:
        conn.close()

    return PublishResult(
        slug=slug, state=status, github_number=github_number,
        projection_deferred=projection_deferred,
    )


def revise_issue(
    issue_number: int,
    *,
    body: Optional[str] = None,
    issue_type: Optional[str] = None,
    feature: Optional[str] = None,
    control_root: Optional[Path] = None,
) -> RevisionResult:
    """Revise an issue-backed work item store-first, then project to GitHub.

    The State Store is authoritative. A store lookup/write failure raises
    :class:`PublishError` and no provider mutation is attempted. The GitHub body
    update is best-effort projection: on failure it is recorded in the outbox so
    a retry path can replay it later.

    ``feature`` is the hop Break 4 was missing (#1635): the CLI accepted the flag
    and this function had no parameter to carry it. A feature that does not
    resolve against ``plan/`` is refused BEFORE the store write, so a refused
    revision never mutates the binding.
    """
    if body is None and issue_type is None and feature is None:
        raise PublishError(
            "revision requires --body-file, --feature and/or explicit --type"
        )

    if feature is not None:
        _require_resolvable_feature(feature, control_root)

    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore
    from atdd.state.work_item_writer import revise_work_item_issue

    try:
        db_path = init_state_store(start=control_root)
        conn = connect(db_path)
    except Exception as exc:
        raise PublishError(
            "State Store unreachable — refusing to revise without the "
            f"authoritative store write: {exc}"
        ) from exc

    projection_deferred = False
    try:
        try:
            obj = revise_work_item_issue(
                conn, issue_number, body=body, issue_type=issue_type,
                feature=feature,
            )
        except Exception as exc:
            raise PublishError(
                f"State Store revision failed for github issue #{issue_number}: {exc}"
            ) from exc

        if body is not None:
            store = StateStore(conn)
            try:
                from atdd.integrations.github.issue_state import update_body

                update_body(issue_number, body)
            except Exception as exc:
                projection_deferred = True
                store.sync.enqueue_outbox(
                    _GITHUB_PROVIDER,
                    _UPDATE_ISSUE_OP,
                    {
                        "issue_number": issue_number,
                        "slug": obj.uid,
                        "body": body,
                        "type": issue_type,
                    },
                )
                logger.warning(
                    "github issue body update deferred to outbox; store revision stands",
                    extra={"issue_number": issue_number, "slug": obj.uid, "error": str(exc)},
                )
    finally:
        conn.close()

    return RevisionResult(
        issue_number=issue_number,
        slug=obj.uid,
        state=obj.state,
        projection_deferred=projection_deferred,
    )
