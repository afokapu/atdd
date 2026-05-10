"""Coach v9 judge call sites — trigger predicates and routing.

This module owns the boundary where deterministic coach routing hands
off to ``atdd judge`` for a §6.9 call site, and shapes the response back
into a coach decision.

Issue #523 ships call site #5 (issue review aggregate ambiguity) per
spec §6.9 #5 / §6.10. Sister issues #522 (call sites #1, #3, #4) and
#O4 (call site #6) extend this module with their own predicates and
routing helpers; the shape established here — pure trigger predicate +
side-effecting router that writes both ``judgments.jsonl`` and
``decisions.jsonl`` — is the discipline.

Public API (call site #5):
  - ``should_fire_issue_review_aggregate(aggregate) -> bool``
  - ``inputs_hash_for_aggregate(*, issue_number, aggregate) -> str``
  - ``invoke_issue_review_aggregate_judge(*, issue_number, aggregate, llm) -> dict``
  - ``route_issue_review_aggregate(*, issue_number, aggregate, llm, coach_run_id) -> dict``

Seams (monkeypatched by integration tests, replaced in production by
real wiring under #J3 / #496):
  - ``post_issue_comment(issue_number, body)`` — GitHub comment writer.
  - ``notify_operator_blocked(issue_number, rationale)`` — operator
    escalation channel.

Both seams default to a no-op + diagnostic so call sites remain
testable without external dependencies.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import jsonschema

from atdd.coach.commands import judge as judge_mod


# ---------------------------------------------------------------------------
# Schema + prompt template paths (frozen at C0 per issue #523)
# ---------------------------------------------------------------------------

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_SCHEMAS_DIR = _PACKAGE_ROOT / "schemas"
_PROMPTS_DIR = _PACKAGE_ROOT / "prompts"

ISSUE_REVIEW_AGGREGATE_CALL_SITE = "issue-review-aggregate"
ISSUE_REVIEW_AGGREGATE_SCHEMA_PATH = (
    _SCHEMAS_DIR / "judge-issue-review-aggregate.response.schema.json"
)
ISSUE_REVIEW_AGGREGATE_PROMPT_PATH = (
    _PROMPTS_DIR / "judge-issue-review-aggregate.prompt.yaml"
)


# ---------------------------------------------------------------------------
# Trigger predicate (call site #5)
# ---------------------------------------------------------------------------


def should_fire_issue_review_aggregate(aggregate: dict) -> bool:
    """Decide whether call site #5 fires for ``aggregate``.

    Per spec §6.9 #5 / §6.10 (and issue #523 scope):

      * ``unanimous-pass``     → false (deterministic short-circuit to
                                 coach-ready; no judge call).
      * ``mixed-verdict``      → true (passes disagree; consolidate).
      * ``unanimous-concern`` AND systemic dimension was flagged by a
        strict subset of the passes → true (single-pass systemic
        concern dominated per §6.10, but the disagreement still
        warrants consolidation rather than a flat block).
      * ``unanimous-concern`` from passes that all flagged the same
        dimension → false (no disagreement to consolidate; coach blocks
        deterministically).
    """
    verdict = aggregate.get("verdict")
    if verdict == "unanimous-pass":
        return False
    if verdict == "mixed-verdict":
        return True
    if verdict != "unanimous-concern":
        return False

    systemic = aggregate["dimensions"]["systemic"]
    if systemic["verdict"] != "concern":
        return False
    n_passes = len(aggregate.get("passes", []))
    n_concern = len(systemic.get("concern_passes", []))
    return 0 < n_concern < n_passes


# ---------------------------------------------------------------------------
# Stable inputs hash (call site #5)
# ---------------------------------------------------------------------------


def _canonical_aggregate(aggregate: dict) -> str:
    """Stable JSON form of ``aggregate`` for hashing.

    Excludes ``generated_at`` so re-running ``atdd issue review`` over
    an unchanged issue body produces an identical hash and the existing
    judgment is cache-resolvable on ``coach --resume``.
    """
    pruned = {k: v for k, v in aggregate.items() if k != "generated_at"}
    if "passes" in pruned:
        pruned = dict(pruned)
        pruned["passes"] = [
            {k: v for k, v in p.items() if k != "timestamp"}
            for p in pruned["passes"]
        ]
    return json.dumps(pruned, sort_keys=True, ensure_ascii=False)


def inputs_hash_for_aggregate(*, issue_number: int, aggregate: dict) -> str:
    """Stable hash of ``(call_site, issue_number, canonical_aggregate)``.

    Identical hashes MUST yield identical responses — the cache key for
    judgment resolution per spec §6.9 (see issue #523 exactly-once
    discipline).
    """
    payload = json.dumps(
        {
            "call_site": ISSUE_REVIEW_AGGREGATE_CALL_SITE,
            "issue_number": issue_number,
            "aggregate": _canonical_aggregate(aggregate),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Judge invocation (call site #5)
# ---------------------------------------------------------------------------


def _resolve_repo_root() -> Path:
    current = Path.cwd().resolve()
    while current != current.parent:
        if (current / ".atdd").is_dir():
            return current
        current = current.parent
    return Path.cwd().resolve()


def _runtime_dir(repo_root: Path) -> Path:
    return repo_root / ".atdd" / "runtime" / "coach"


def _append_judgment_record(
    repo_root: Path,
    *,
    judgment_id: str,
    inputs_hash: str,
    response: Optional[dict],
    outcome: str,
    cached: bool,
    model: Optional[str],
    call_site: str = ISSUE_REVIEW_AGGREGATE_CALL_SITE,
) -> None:
    record = {
        "judgment_id": judgment_id,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "call_site": call_site,
        "inputs_hash": inputs_hash,
        "response": response,
        "cached": cached,
        "outcome": outcome,
    }
    if model is not None:
        record["model"] = model
    log_dir = _runtime_dir(repo_root)
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "judgments.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_response_schema() -> dict:
    return json.loads(ISSUE_REVIEW_AGGREGATE_SCHEMA_PATH.read_text())


def invoke_issue_review_aggregate_judge(
    *,
    issue_number: int,
    aggregate: dict,
    llm: Optional[str] = None,
) -> dict:
    """Invoke ``atdd judge`` for call site #5 if the predicate fires.

    Returns ``{"fired": bool, "response": dict | None, "judgment_id": str | None,
    "inputs_hash": str | None, "outcome": str}``. Never raises for
    documented failure modes — the caller routes on ``response["decision"]``
    when fired and on the deterministic short-circuit when not.
    """
    if not should_fire_issue_review_aggregate(aggregate):
        return {
            "fired": False,
            "response": None,
            "judgment_id": None,
            "inputs_hash": None,
            "outcome": "skipped",
        }

    repo_root = _resolve_repo_root()
    inputs_hash = inputs_hash_for_aggregate(
        issue_number=issue_number, aggregate=aggregate
    )
    judgment_id = str(uuid.uuid4())

    factory = judge_mod.LLM_REGISTRY.get(llm) if llm else None
    if factory is None:
        _append_judgment_record(
            repo_root,
            judgment_id=judgment_id,
            inputs_hash=inputs_hash,
            response=None,
            outcome="llm_unavailable",
            cached=False,
            model=llm,
        )
        print(
            f"call site #5 (issue-review-aggregate): unknown LLM {llm!r}",
            file=sys.stderr,
        )
        return {
            "fired": True,
            "response": None,
            "judgment_id": judgment_id,
            "inputs_hash": inputs_hash,
            "outcome": "llm_unavailable",
        }

    try:
        client = factory()
        response = client.invoke(_render_prompt_for_call_site(issue_number, aggregate))
    except judge_mod.LLMUnavailable as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(
            f"call site #5 (issue-review-aggregate): LLM unavailable: {exc}",
            file=sys.stderr,
        )
        _append_judgment_record(
            repo_root,
            judgment_id=judgment_id,
            inputs_hash=inputs_hash,
            response=None,
            outcome="llm_unavailable",
            cached=False,
            model=llm,
        )
        return {
            "fired": True,
            "response": None,
            "judgment_id": judgment_id,
            "inputs_hash": inputs_hash,
            "outcome": "llm_unavailable",
        }

    schema = _load_response_schema()
    try:
        jsonschema.Draft202012Validator(schema).validate(response)
    except jsonschema.ValidationError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(
            f"call site #5 (issue-review-aggregate): response failed schema "
            f"validation at {'.'.join(str(p) for p in exc.absolute_path) or '<root>'}: "
            f"{exc.message}",
            file=sys.stderr,
        )
        _append_judgment_record(
            repo_root,
            judgment_id=judgment_id,
            inputs_hash=inputs_hash,
            response=response,
            outcome="schema_violation",
            cached=False,
            model=llm,
        )
        return {
            "fired": True,
            "response": response,
            "judgment_id": judgment_id,
            "inputs_hash": inputs_hash,
            "outcome": "schema_violation",
        }

    _append_judgment_record(
        repo_root,
        judgment_id=judgment_id,
        inputs_hash=inputs_hash,
        response=response,
        outcome="ok",
        cached=False,
        model=llm,
    )
    return {
        "fired": True,
        "response": response,
        "judgment_id": judgment_id,
        "inputs_hash": inputs_hash,
        "outcome": "ok",
    }


def _render_prompt_for_call_site(issue_number: int, aggregate: dict) -> str:
    """Render the call site #5 prompt from the YAML template.

    Tests don't observe the rendered prompt — only the stub LLM response
    matters — but production runs need the substituted body.
    """
    import yaml

    raw = yaml.safe_load(ISSUE_REVIEW_AGGREGATE_PROMPT_PATH.read_text())
    body = raw["prompt"]
    return body.format(
        issue_number=issue_number,
        pass_count=len(aggregate.get("passes", [])),
        aggregate_json=json.dumps(aggregate, ensure_ascii=False, indent=2),
        findings_json=json.dumps(
            aggregate.get("findings", []), ensure_ascii=False, indent=2
        ),
    )


# ---------------------------------------------------------------------------
# Routing (call site #5)
# ---------------------------------------------------------------------------


def post_issue_comment(*, issue_number: int, body: str) -> int:
    """Post `body` as a GitHub comment on `issue_number` via `gh`.

    Tests monkeypatch this seam to capture the body without shelling
    out to a real `gh`.
    """
    proc = subprocess.run(
        ["gh", "issue", "comment", str(issue_number), "--body", body],
        check=False,
    )
    return proc.returncode


def notify_operator_blocked(*, issue_number: int, rationale: str) -> int:
    """Notify the operator that ``issue_number`` was escalated to BLOCKED.

    Default implementation prints to stderr; integration runners
    monkeypatch this to route to the configured escalation channel.
    """
    print(
        f"[operator-escalation] issue #{issue_number} BLOCKED: {rationale}",
        file=sys.stderr,
    )
    return 0


def _append_decision_record(
    repo_root: Path,
    *,
    decision_type: str,
    issue_number: int,
    coach_run_id: str,
    inputs: dict,
    outcome: dict,
    judgment_id: Optional[str],
    rationale: Optional[str] = None,
) -> str:
    decision_id = str(uuid.uuid4())
    record = {
        "decision_id": decision_id,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "coach_run_id": coach_run_id,
        "issue_number": issue_number,
        "decision_type": decision_type,
        "inputs": inputs,
        "outcome": outcome,
    }
    if rationale is not None:
        record["rationale"] = rationale
    if judgment_id is not None:
        record["judgment_id"] = judgment_id
    log_dir = _runtime_dir(repo_root)
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "decisions.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return decision_id


def route_issue_review_aggregate(
    *,
    issue_number: int,
    aggregate: dict,
    llm: Optional[str] = None,
    coach_run_id: str,
) -> dict:
    """Invoke call site #5 (if it fires) and execute the routing branch.

    Branches per spec §6.9 #5 (issue #523):

      * ``unanimous-pass`` (or other non-firing aggregates that already
        classify to ``proceed``): emit a ``coach_ready`` decision; no
        judge call.
      * ``accept``: emit a ``coach_ready`` decision referencing the
        ``judgment_id``.
      * ``request_revision``: post ``consolidated_feedback`` as a
        GitHub *issue* comment (not PR — pre-coach is before the PR
        exists) and emit ``pre_coach_paused``.
      * ``escalate``: transition issue state to BLOCKED, notify the
        operator with the rationale, emit an ``escalation`` decision.

    Returns a dict with at least ``decision`` and ``state`` keys; tests
    inspect the persistent records under ``.atdd/runtime/coach/`` for
    the durable contract.
    """
    repo_root = _resolve_repo_root()
    invocation = invoke_issue_review_aggregate_judge(
        issue_number=issue_number, aggregate=aggregate, llm=llm
    )

    if not invocation["fired"]:
        # Deterministic short-circuit — unanimous-pass (or other
        # non-firing aggregates). Coach proceeds.
        _append_decision_record(
            repo_root,
            decision_type="coach_ready",
            issue_number=issue_number,
            coach_run_id=coach_run_id,
            inputs={"verdict": aggregate.get("verdict")},
            outcome={"state": "READY"},
            judgment_id=None,
        )
        return {
            "decision": "accept",
            "fired": False,
            "state": "READY",
            "judgment_id": None,
        }

    if invocation["outcome"] != "ok":
        # LLM failure path — surface the gap so the operator sees it.
        _append_decision_record(
            repo_root,
            decision_type="escalation",
            issue_number=issue_number,
            coach_run_id=coach_run_id,
            inputs={"verdict": aggregate.get("verdict")},
            outcome={"state": "BLOCKED", "reason": invocation["outcome"]},
            judgment_id=invocation["judgment_id"],
            rationale=f"call site #5 {invocation['outcome']}",
        )
        notify_operator_blocked(
            issue_number=issue_number,
            rationale=f"call site #5 {invocation['outcome']}",
        )
        return {
            "decision": "escalate",
            "fired": True,
            "state": "BLOCKED",
            "judgment_id": invocation["judgment_id"],
        }

    response = invocation["response"]
    decision = response["decision"]
    judgment_id = invocation["judgment_id"]
    feedback = response["consolidated_feedback"]

    if decision == "accept":
        _append_decision_record(
            repo_root,
            decision_type="coach_ready",
            issue_number=issue_number,
            coach_run_id=coach_run_id,
            inputs={"verdict": aggregate.get("verdict")},
            outcome={"state": "READY"},
            judgment_id=judgment_id,
            rationale=feedback,
        )
        return {
            "decision": "accept",
            "fired": True,
            "state": "READY",
            "judgment_id": judgment_id,
        }

    if decision == "request_revision":
        post_issue_comment(
            issue_number=issue_number,
            body=_format_request_revision_comment(feedback, response),
        )
        _append_decision_record(
            repo_root,
            decision_type="pre_coach_paused",
            issue_number=issue_number,
            coach_run_id=coach_run_id,
            inputs={"verdict": aggregate.get("verdict")},
            outcome={"state": "PRE_COACH_PAUSED"},
            judgment_id=judgment_id,
            rationale=feedback,
        )
        return {
            "decision": "request_revision",
            "fired": True,
            "state": "PRE_COACH_PAUSED",
            "judgment_id": judgment_id,
        }

    # decision == "escalate"
    notify_operator_blocked(issue_number=issue_number, rationale=feedback)
    _append_decision_record(
        repo_root,
        decision_type="escalation",
        issue_number=issue_number,
        coach_run_id=coach_run_id,
        inputs={"verdict": aggregate.get("verdict")},
        outcome={"state": "BLOCKED"},
        judgment_id=judgment_id,
        rationale=feedback,
    )
    return {
        "decision": "escalate",
        "fired": True,
        "state": "BLOCKED",
        "judgment_id": judgment_id,
    }


def _format_request_revision_comment(feedback: str, response: dict) -> str:
    """Render the GitHub-issue comment body for ``request_revision``."""
    dims = ", ".join(f"`{d}`" for d in response.get("dominant_dimensions", []))
    return (
        "## Pre-coach review — revision requested\n"
        "\n"
        f"**Dominant dimensions:** {dims or '_(none reported)_'}\n"
        "\n"
        f"{feedback}\n"
        "\n"
        "_Posted by `atdd judge` call site #5 (issue review aggregate consolidation)._\n"
    )


# =============================================================================
# Call site #1 — borderline tier-1 (spec §6.9 #1, issue #522)
# =============================================================================


BORDERLINE_TIER1_CALL_SITE = "borderline-tier1"
BORDERLINE_TIER1_SCHEMA_PATH = (
    _SCHEMAS_DIR / "judge-borderline-tier1.response.schema.json"
)
BORDERLINE_TIER1_PROMPT_PATH = (
    _PROMPTS_DIR / "judge-borderline-tier1.prompt.yaml"
)


def _parse_location_path(location: str) -> str:
    """Extract just the file path from a 'path:line' or 'path:line:col' string."""
    parts = location.split(":")
    return parts[0] if parts else location


def _locations_near(any_loc: str, edited: list[str], tolerance: int = 5) -> bool:
    """Check if any edited line is within ``tolerance`` lines of ``any_loc``."""
    parts = any_loc.split(":")
    if len(parts) < 2:
        return False
    try:
        loc_line = int(parts[-1])
    except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return False
    loc_path = parts[0]
    for edited_loc in edited:
        e_parts = edited_loc.split(":")
        if len(e_parts) < 2:
            continue
        e_path = e_parts[0]
        if e_path != loc_path:
            continue
        try:
            e_line = int(e_parts[-1])
        except ValueError:
            continue
        if abs(loc_line - e_line) <= tolerance:
            return True
    return False


def should_fire_borderline_tier1(context: dict) -> bool:
    """Decide whether call site #1 fires for the given tier-1 context.

    Per spec §6.9 #1 / issue #522:
      * Mixed pass/fail with ambiguous severity (some violations at sev 1-3
        while other rules pass) → fires.
      * suppress-and-clean rule cluster touching recently-edited lines → fires.
      * Clean pass or all-fail with high severity → does NOT fire.
    """
    violations = context.get("violations", [])
    total_rules = context.get("total_rules", 0)
    recently_edited = context.get("recently_edited_lines", [])

    if not violations:
        return False

    # Check suppress-and-clean cluster near recent edits
    suppress_violations = [
        v for v in violations if v.get("disposition") == "suppress-and-clean"
    ]
    if suppress_violations and recently_edited:
        for v in suppress_violations:
            if _locations_near(v.get("location", ""), recently_edited):
                return True

    # Check mixed pass/fail with ambiguous severity (severity <= 3 suggests
    # advisory-level, not definitively blocking). Only consider strict-
    # disposition violations — suppress-and-clean ones are handled by the
    # deterministic suppression scanner.
    strict_violations = [v for v in violations if v.get("disposition") != "suppress-and-clean"]
    has_ambiguous = any(v.get("severity", 5) <= 3 for v in strict_violations)
    passing = total_rules - len(violations)
    if has_ambiguous and passing > 0:
        return True

    return False


def _load_borderline_tier1_schema() -> dict:
    return json.loads(BORDERLINE_TIER1_SCHEMA_PATH.read_text())


def invoke_borderline_tier1_judge(
    *,
    context: dict,
    llm: Optional[str] = None,
) -> dict:
    """Invoke ``attd judge`` for call site #1 if the predicate fires."""
    if not should_fire_borderline_tier1(context):
        return {
            "fired": False,
            "response": None,
            "judgment_id": None,
            "inputs_hash": None,
            "outcome": "skipped",
        }

    repo_root = _resolve_repo_root()
    inputs_hash = hashlib.sha256(
        json.dumps(
            {"call_site": BORDERLINE_TIER1_CALL_SITE, "violations": context.get("violations", [])},
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    judgment_id = str(uuid.uuid4())

    factory = judge_mod.LLM_REGISTRY.get(llm) if llm else None
    if factory is None:
        _append_judgment_record(
            repo_root,
            judgment_id=judgment_id,
            inputs_hash=inputs_hash,
            response=None,
            outcome="llm_unavailable",
            cached=False,
            model=llm,
            call_site=BORDERLINE_TIER1_CALL_SITE,
        )
        print(
            f"call site #1 (borderline-tier1): unknown LLM {llm!r}",
            file=sys.stderr,
        )
        return {
            "fired": True,
            "response": None,
            "judgment_id": judgment_id,
            "inputs_hash": inputs_hash,
            "outcome": "llm_unavailable",
        }

    try:
        client = factory()
        response = client.invoke(
            f"Judge borderline tier-1 result: {json.dumps(context, ensure_ascii=False)}"
        )
    except judge_mod.LLMUnavailable as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(
            f"call site #1 (borderline-tier1): LLM unavailable: {exc}",
            file=sys.stderr,
        )
        _append_judgment_record(
            repo_root,
            judgment_id=judgment_id,
            inputs_hash=inputs_hash,
            response=None,
            outcome="llm_unavailable",
            cached=False,
            model=llm,
            call_site=BORDERLINE_TIER1_CALL_SITE,
        )
        return {
            "fired": True,
            "response": None,
            "judgment_id": judgment_id,
            "inputs_hash": inputs_hash,
            "outcome": "llm_unavailable",
        }

    schema = _load_borderline_tier1_schema()
    try:
        jsonschema.Draft202012Validator(schema).validate(response)
    except jsonschema.ValidationError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(
            f"call site #1 (borderline-tier1): schema validation failed: {exc.message}",
            file=sys.stderr,
        )
        _append_judgment_record(
            repo_root,
            judgment_id=judgment_id,
            inputs_hash=inputs_hash,
            response=response,
            outcome="schema_violation",
            cached=False,
            model=llm,
            call_site=BORDERLINE_TIER1_CALL_SITE,
        )
        return {
            "fired": True,
            "response": response,
            "judgment_id": judgment_id,
            "inputs_hash": inputs_hash,
            "outcome": "schema_violation",
        }

    _append_judgment_record(
        repo_root,
        judgment_id=judgment_id,
        inputs_hash=inputs_hash,
        response=response,
        outcome="ok",
        cached=False,
        model=llm,
        call_site=BORDERLINE_TIER1_CALL_SITE,
    )
    return {
        "fired": True,
        "response": response,
        "judgment_id": judgment_id,
        "inputs_hash": inputs_hash,
        "outcome": "ok",
    }


def post_pr_annotation(*, rationale: str, **kwargs) -> int:
    """Post a PR annotation with the judge rationale. Tests monkeypatch this."""
    print(f"[pr-annotation] {rationale}", file=sys.stderr)
    return 0


def route_borderline_tier1(
    *,
    context: dict,
    llm: Optional[str] = None,
    coach_run_id: str,
) -> dict:
    """Invoke call site #1 (if it fires) and execute the routing branch."""
    repo_root = _resolve_repo_root()
    invocation = invoke_borderline_tier1_judge(context=context, llm=llm)

    if not invocation["fired"]:
        _append_decision_record(
            repo_root,
            decision_type="coach_ready",
            issue_number=0,
            coach_run_id=coach_run_id,
            inputs={"violations": len(context.get("violations", []))},
            outcome={"state": "READY"},
            judgment_id=None,
        )
        return {"decision": "pass", "fired": False, "state": "READY", "judgment_id": None}

    if invocation["outcome"] != "ok":
        _append_decision_record(
            repo_root,
            decision_type="escalation",
            issue_number=0,
            coach_run_id=coach_run_id,
            inputs={"violations": len(context.get("violations", []))},
            outcome={"state": "BLOCKED", "reason": invocation["outcome"]},
            judgment_id=invocation["judgment_id"],
            rationale=f"call site #1 {invocation['outcome']}",
        )
        notify_operator_blocked(
            issue_number=0,
            rationale=f"call site #1 {invocation['outcome']}",
        )
        return {
            "decision": "block",
            "fired": True,
            "state": "BLOCKED",
            "judgment_id": invocation["judgment_id"],
        }

    response = invocation["response"]
    decision = response["decision"]
    judgment_id = invocation["judgment_id"]
    rationale = response["rationale"]

    if decision == "pass":
        _append_decision_record(
            repo_root,
            decision_type="coach_ready",
            issue_number=0,
            coach_run_id=coach_run_id,
            inputs={"violations": len(context.get("violations", []))},
            outcome={"state": "READY"},
            judgment_id=judgment_id,
            rationale=rationale,
        )
        return {
            "decision": "pass",
            "fired": True,
            "state": "READY",
            "judgment_id": judgment_id,
        }

    if decision == "respawn":
        _append_decision_record(
            repo_root,
            decision_type="spawn_feedback",
            issue_number=0,
            coach_run_id=coach_run_id,
            inputs={"violations": len(context.get("violations", []))},
            outcome={"state": "RESPAWN"},
            judgment_id=judgment_id,
            rationale=rationale,
        )
        return {
            "decision": "respawn",
            "fired": True,
            "state": "RESPAWN",
            "judgment_id": judgment_id,
        }

    # decision == "annotate"
    post_pr_annotation(rationale=rationale)
    _append_decision_record(
        repo_root,
        decision_type="pr_annotation",
        issue_number=0,
        coach_run_id=coach_run_id,
        inputs={"violations": len(context.get("violations", []))},
        outcome={"state": "ANNOTATED"},
        judgment_id=judgment_id,
        rationale=rationale,
    )
    return {
        "decision": "annotate",
        "fired": True,
        "state": "ANNOTATED",
        "judgment_id": judgment_id,
    }


# =============================================================================
# Call site #3 — retry-vs-escalate (spec §6.9 #3, issue #522)
# =============================================================================


RETRY_VS_ESCALATE_CALL_SITE = "retry-vs-escalate"
RETRY_VS_ESCALATE_SCHEMA_PATH = (
    _SCHEMAS_DIR / "judge-retry-vs-escalate.response.schema.json"
)


def should_fire_retry_vs_escalate(context: dict) -> bool:
    """Decide whether call site #3 fires.

    Per spec §6.9 #3: fires when ``retry_count == max_retries - 1``,
    i.e. the *next* attempt would consume the final retry.
    """
    retry_count = context.get("retry_count", 0)
    max_retries = context.get("max_retries", 0)
    return retry_count == max_retries - 1


def _load_retry_vs_escalate_schema() -> dict:
    return json.loads(RETRY_VS_ESCALATE_SCHEMA_PATH.read_text())


def invoke_retry_vs_escalate_judge(
    *,
    context: dict,
    llm: Optional[str] = None,
) -> dict:
    """Invoke ``attd judge`` for call site #3 if the predicate fires."""
    if not should_fire_retry_vs_escalate(context):
        return {
            "fired": False,
            "response": None,
            "judgment_id": None,
            "inputs_hash": None,
            "outcome": "skipped",
        }

    repo_root = _resolve_repo_root()
    inputs_hash = hashlib.sha256(
        json.dumps(
            {"call_site": RETRY_VS_ESCALATE_CALL_SITE, "context": context},
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    judgment_id = str(uuid.uuid4())

    factory = judge_mod.LLM_REGISTRY.get(llm) if llm else None
    if factory is None:
        _append_judgment_record(
            repo_root,
            judgment_id=judgment_id,
            inputs_hash=inputs_hash,
            response=None,
            outcome="llm_unavailable",
            cached=False,
            model=llm,
            call_site=RETRY_VS_ESCALATE_CALL_SITE,
        )
        print(
            f"call site #3 (retry-vs-escalate): unknown LLM {llm!r}",
            file=sys.stderr,
        )
        return {
            "fired": True,
            "response": None,
            "judgment_id": judgment_id,
            "inputs_hash": inputs_hash,
            "outcome": "llm_unavailable",
        }

    try:
        client = factory()
        response = client.invoke(
            f"Judge retry-vs-escalate: {json.dumps(context, ensure_ascii=False)}"
        )
    except judge_mod.LLMUnavailable as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(
            f"call site #3 (retry-vs-escalate): LLM unavailable: {exc}",
            file=sys.stderr,
        )
        _append_judgment_record(
            repo_root,
            judgment_id=judgment_id,
            inputs_hash=inputs_hash,
            response=None,
            outcome="llm_unavailable",
            cached=False,
            model=llm,
            call_site=RETRY_VS_ESCALATE_CALL_SITE,
        )
        return {
            "fired": True,
            "response": None,
            "judgment_id": judgment_id,
            "inputs_hash": inputs_hash,
            "outcome": "llm_unavailable",
        }

    schema = _load_retry_vs_escalate_schema()
    try:
        jsonschema.Draft202012Validator(schema).validate(response)
    except jsonschema.ValidationError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(
            f"call site #3 (retry-vs-escalate): schema validation failed: {exc.message}",
            file=sys.stderr,
        )
        _append_judgment_record(
            repo_root,
            judgment_id=judgment_id,
            inputs_hash=inputs_hash,
            response=response,
            outcome="schema_violation",
            cached=False,
            model=llm,
            call_site=RETRY_VS_ESCALATE_CALL_SITE,
        )
        return {
            "fired": True,
            "response": response,
            "judgment_id": judgment_id,
            "inputs_hash": inputs_hash,
            "outcome": "schema_violation",
        }

    _append_judgment_record(
        repo_root,
        judgment_id=judgment_id,
        inputs_hash=inputs_hash,
        response=response,
        outcome="ok",
        cached=False,
        model=llm,
        call_site=RETRY_VS_ESCALATE_CALL_SITE,
    )
    return {
        "fired": True,
        "response": response,
        "judgment_id": judgment_id,
        "inputs_hash": inputs_hash,
        "outcome": "ok",
    }


def route_retry_vs_escalate(
    *,
    context: dict,
    llm: Optional[str] = None,
    coach_run_id: str,
) -> dict:
    """Invoke call site #3 (if it fires) and execute the routing branch."""
    repo_root = _resolve_repo_root()
    invocation = invoke_retry_vs_escalate_judge(context=context, llm=llm)

    if not invocation["fired"]:
        return {"decision": "skip", "fired": False, "state": "CONTINUE", "judgment_id": None}

    if invocation["outcome"] != "ok":
        _append_decision_record(
            repo_root,
            decision_type="escalation",
            issue_number=0,
            coach_run_id=coach_run_id,
            inputs={"retry_count": context.get("retry_count")},
            outcome={"state": "BLOCKED", "reason": invocation["outcome"]},
            judgment_id=invocation["judgment_id"],
            rationale=f"call site #3 {invocation['outcome']}",
        )
        notify_operator_blocked(
            issue_number=0,
            rationale=f"call site #3 {invocation['outcome']}",
        )
        return {
            "decision": "escalate",
            "fired": True,
            "state": "BLOCKED",
            "judgment_id": invocation["judgment_id"],
        }

    response = invocation["response"]
    decision = response["decision"]
    judgment_id = invocation["judgment_id"]
    reasoning = response["reasoning"]

    if decision == "retry":
        _append_decision_record(
            repo_root,
            decision_type="continue",
            issue_number=0,
            coach_run_id=coach_run_id,
            inputs={"retry_count": context.get("retry_count")},
            outcome={"state": "CONTINUE"},
            judgment_id=judgment_id,
            rationale=reasoning,
        )
        return {
            "decision": "retry",
            "fired": True,
            "state": "CONTINUE",
            "judgment_id": judgment_id,
        }

    # decision == "escalate"
    notify_operator_blocked(issue_number=0, rationale=reasoning)
    _append_decision_record(
        repo_root,
        decision_type="escalation",
        issue_number=0,
        coach_run_id=coach_run_id,
        inputs={"retry_count": context.get("retry_count")},
        outcome={"state": "BLOCKED"},
        judgment_id=judgment_id,
        rationale=reasoning,
    )
    return {
        "decision": "escalate",
        "fired": True,
        "state": "BLOCKED",
        "judgment_id": judgment_id,
    }


# =============================================================================
# Call site #4 — cross-phase regression (spec §6.9 #4, issue #522)
# =============================================================================


CROSS_PHASE_REGRESSION_CALL_SITE = "cross-phase-regression"
CROSS_PHASE_REGRESSION_SCHEMA_PATH = (
    _SCHEMAS_DIR / "judge-cross-phase-regression.response.schema.json"
)


def _violation_key(v: dict) -> str:
    """Stable key for violation comparison: rule_id + location."""
    return f"{v.get('rule_id', '')}:{v.get('location', '')}"


def should_fire_cross_phase_regression(context: dict) -> bool:
    """Decide whether call site #4 fires.

    Per spec §6.9 #4: fires when tier-1 in a later phase reveals
    violations that did not exist at the predecessor phase's exit commit.
    """
    current = context.get("current_violations", [])
    predecessor = context.get("predecessor_exit_violations", [])
    if not current:
        return False

    predecessor_keys = {_violation_key(v) for v in predecessor}
    for v in current:
        if _violation_key(v) not in predecessor_keys:
            return True
    return False


def _load_cross_phase_regression_schema() -> dict:
    return json.loads(CROSS_PHASE_REGRESSION_SCHEMA_PATH.read_text())


def invoke_cross_phase_regression_judge(
    *,
    context: dict,
    llm: Optional[str] = None,
) -> dict:
    """Invoke ``attd judge`` for call site #4 if the predicate fires."""
    if not should_fire_cross_phase_regression(context):
        return {
            "fired": False,
            "response": None,
            "judgment_id": None,
            "inputs_hash": None,
            "outcome": "skipped",
        }

    repo_root = _resolve_repo_root()
    inputs_hash = hashlib.sha256(
        json.dumps(
            {"call_site": CROSS_PHASE_REGRESSION_CALL_SITE, "context": context},
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    judgment_id = str(uuid.uuid4())

    factory = judge_mod.LLM_REGISTRY.get(llm) if llm else None
    if factory is None:
        _append_judgment_record(
            repo_root,
            judgment_id=judgment_id,
            inputs_hash=inputs_hash,
            response=None,
            outcome="llm_unavailable",
            cached=False,
            model=llm,
            call_site=CROSS_PHASE_REGRESSION_CALL_SITE,
        )
        print(
            f"call site #4 (cross-phase-regression): unknown LLM {llm!r}",
            file=sys.stderr,
        )
        return {
            "fired": True,
            "response": None,
            "judgment_id": judgment_id,
            "inputs_hash": inputs_hash,
            "outcome": "llm_unavailable",
        }

    try:
        client = factory()
        response = client.invoke(
            f"Judge cross-phase regression: {json.dumps(context, ensure_ascii=False)}"
        )
    except judge_mod.LLMUnavailable as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(
            f"call site #4 (cross-phase-regression): LLM unavailable: {exc}",
            file=sys.stderr,
        )
        _append_judgment_record(
            repo_root,
            judgment_id=judgment_id,
            inputs_hash=inputs_hash,
            response=None,
            outcome="llm_unavailable",
            cached=False,
            model=llm,
            call_site=CROSS_PHASE_REGRESSION_CALL_SITE,
        )
        return {
            "fired": True,
            "response": None,
            "judgment_id": judgment_id,
            "inputs_hash": inputs_hash,
            "outcome": "llm_unavailable",
        }

    schema = _load_cross_phase_regression_schema()
    try:
        jsonschema.Draft202012Validator(schema).validate(response)
    except jsonschema.ValidationError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(
            f"call site #4 (cross-phase-regression): schema validation failed: {exc.message}",
            file=sys.stderr,
        )
        _append_judgment_record(
            repo_root,
            judgment_id=judgment_id,
            inputs_hash=inputs_hash,
            response=response,
            outcome="schema_violation",
            cached=False,
            model=llm,
            call_site=CROSS_PHASE_REGRESSION_CALL_SITE,
        )
        return {
            "fired": True,
            "response": response,
            "judgment_id": judgment_id,
            "inputs_hash": inputs_hash,
            "outcome": "schema_violation",
        }

    _append_judgment_record(
        repo_root,
        judgment_id=judgment_id,
        inputs_hash=inputs_hash,
        response=response,
        outcome="ok",
        cached=False,
        model=llm,
        call_site=CROSS_PHASE_REGRESSION_CALL_SITE,
    )
    return {
        "fired": True,
        "response": response,
        "judgment_id": judgment_id,
        "inputs_hash": inputs_hash,
        "outcome": "ok",
    }


def route_cross_phase_regression(
    *,
    context: dict,
    llm: Optional[str] = None,
    coach_run_id: str,
) -> dict:
    """Invoke call site #4 (if it fires) and execute the routing branch."""
    repo_root = _resolve_repo_root()
    invocation = invoke_cross_phase_regression_judge(context=context, llm=llm)

    if not invocation["fired"]:
        return {"decision": "skip", "fired": False, "state": "CONTINUE", "judgment_id": None}

    if invocation["outcome"] != "ok":
        _append_decision_record(
            repo_root,
            decision_type="escalation",
            issue_number=0,
            coach_run_id=coach_run_id,
            inputs={"phase": context.get("current_phase")},
            outcome={"state": "BLOCKED", "reason": invocation["outcome"]},
            judgment_id=invocation["judgment_id"],
            rationale=f"call site #4 {invocation['outcome']}",
        )
        notify_operator_blocked(
            issue_number=0,
            rationale=f"call site #4 {invocation['outcome']}",
        )
        return {
            "decision": "escalate",
            "fired": True,
            "state": "BLOCKED",
            "judgment_id": invocation["judgment_id"],
        }

    response = invocation["response"]
    decision = response["decision"]
    judgment_id = invocation["judgment_id"]
    rationale = response["rationale"]
    target_phase = response["target_phase"]

    if decision == "fix_in_place":
        _append_decision_record(
            repo_root,
            decision_type="continue",
            issue_number=0,
            coach_run_id=coach_run_id,
            inputs={"phase": context.get("current_phase")},
            outcome={"state": "CONTINUE"},
            judgment_id=judgment_id,
            rationale=rationale,
        )
        return {
            "decision": "fix_in_place",
            "fired": True,
            "state": "CONTINUE",
            "target_phase": target_phase,
            "judgment_id": judgment_id,
        }

    if decision == "reopen_prior_phase":
        _append_decision_record(
            repo_root,
            decision_type="phase_rollback",
            issue_number=0,
            coach_run_id=coach_run_id,
            inputs={"phase": context.get("current_phase")},
            outcome={"state": "ROLLED_BACK", "target_phase": target_phase},
            judgment_id=judgment_id,
            rationale=rationale,
        )
        return {
            "decision": "reopen_prior_phase",
            "fired": True,
            "state": "ROLLED_BACK",
            "target_phase": target_phase,
            "judgment_id": judgment_id,
        }

    # decision == "escalate"
    notify_operator_blocked(issue_number=0, rationale=rationale)
    _append_decision_record(
        repo_root,
        decision_type="escalation",
        issue_number=0,
        coach_run_id=coach_run_id,
        inputs={"phase": context.get("current_phase")},
        outcome={"state": "BLOCKED"},
        judgment_id=judgment_id,
        rationale=rationale,
    )
    return {
        "decision": "escalate",
        "fired": True,
        "state": "BLOCKED",
        "judgment_id": judgment_id,
    }
