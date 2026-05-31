"""events.jsonl schema contract (docs/coach-decomposition.md §5.2).

The train runner is the *single writer* to ``runs/<run_id>/events.jsonl``. Every
line is a JSON object with the required top-level fields below plus a
type-specific ``payload``. This module freezes the schema version and the initial
event-type registry; it contains only pure data + pure validation helpers (no
I/O) so it is safe to import from anywhere.

Concrete appending/replay ships with ``JsonlPersistenceStore`` in Child 7
(#894). See :class:`atdd.train.types.TrainEvent` for the in-memory shape.
"""
from __future__ import annotations

# Schema-version rule (§5.2): any new ``type`` or payload-shape change increments
# the minor; a breaking format change increments the major. Replay refuses
# unknown major versions and migrates minor versions in-memory at read time.
SCHEMA_VERSION = "1.0"

# Required top-level keys on every events.jsonl line (§5.2 + TrainEvent §4.7).
REQUIRED_EVENT_FIELDS: tuple[str, ...] = (
    "schema_version",
    "ts",
    "run_id",
    "issue_number",
    "type",
    "payload",
    "seq",
)

# Initial event-type set (§5.2). Maps event ``type`` → required ``payload`` keys.
# Sourced-from / single-writer notes live in the spec; this is the machine copy.
EVENT_TYPES: dict[str, tuple[str, ...]] = {
    "RunStarted": ("conventions_hash", "conventions_snapshot_ref", "policy_handle_id"),
    "EvidenceMaterialized": ("evidence_hash", "current_phase"),
    "DecisionMade": ("verdict_kind", "from_phase", "to_phase", "persona", "rule_ids"),
    "DispatchEmitted": ("dispatch_spec",),
    "AgentSpawned": ("agent_id", "transport", "surface_ref"),
    "AgentReady": ("agent_id", "transport_signal", "elapsed_seconds"),
    "AgentEventReceived": ("agent_id", "agent_event"),
    "AgentDone": ("agent_id", "summary", "exit_code"),
    "PhaseAdvanced": ("from_phase", "to_phase", "commit_sha"),
    "PrOpened": ("pr_number", "branch"),
    "PrMerged": ("pr_number", "merge_commit_sha"),
    "RunBlocked": ("verdict",),
    "RunEscalated": ("verdict", "notification_channel"),
    "RunCompleted": ("final_phase", "total_duration_seconds"),
    "RunResumed": ("from_event_seq", "resume_reason"),
    # Added in Child 8 (#895): the TrainRunner.cancel control event. Demonstrates
    # that a new event type is a pure events.jsonl schema bump — no Coach-core
    # change (Coach-core never imports atdd.train.events).
    "RunCancelled": ("reason",),
}


def schema_major(version: str) -> int:
    """Major component of a ``"major.minor"`` schema version string. Pure."""
    return int(version.split(".", 1)[0])


def validate_event_dict(event: dict) -> tuple[str, ...]:
    """Return a tuple of human-readable problems with ``event``; empty == valid.

    Pure: no I/O, no clock. Checks required top-level fields, a known ``type``,
    and the required payload keys for that type. Does not assert payload value
    shapes beyond presence (those are owned by the producing layer).
    """
    problems: list[str] = []

    for field in REQUIRED_EVENT_FIELDS:
        if field not in event:
            problems.append(f"missing required field {field!r}")

    version = event.get("schema_version")
    if version is not None and schema_major(str(version)) != schema_major(SCHEMA_VERSION):
        problems.append(
            f"unsupported schema major: {version!r} (reader supports {SCHEMA_VERSION!r})"
        )

    etype = event.get("type")
    if etype is not None:
        if etype not in EVENT_TYPES:
            problems.append(f"unknown event type {etype!r}")
        else:
            payload = event.get("payload")
            if not isinstance(payload, dict):
                problems.append("payload must be an object")
            else:
                for key in EVENT_TYPES[etype]:
                    if key not in payload:
                        problems.append(f"{etype} payload missing {key!r}")

    return tuple(problems)


__all__ = [
    "SCHEMA_VERSION",
    "REQUIRED_EVENT_FIELDS",
    "EVENT_TYPES",
    "schema_major",
    "validate_event_dict",
]
