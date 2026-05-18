"""`atdd observer <subcommand>` — coach v9 observer (issues #500 + #515 + #516).

Event-driven detect-and-correct sidecar per agent. Tails the agent's
``output.log``, watches the worktree, evaluates a YAML-discovered rule
registry, and dispatches corrections through one of three injection
paths (CLI return-path / multiplexer send-keys / kill-and-respawn).

This module owns the *runtime* + *registry* + *injection* foundation
(skeleton from #500), plus the *operator-facing dashboard* absorbed
from ``commands/babysit.py`` per spec §0.2 (issue #515 / L6):

- ``SurfaceRow`` — one rendered row of the dashboard. Pure data.
- ``_format_hms`` — duration formatter.
- ``_render_dashboard`` — pure renderer of the aggregate table.
- ``_extract_surface_state_from_runtime`` — build a ``SurfaceRow``
  from ``.atdd/runtime/agents/<id>/`` (heartbeat.json, context.json,
  optional token-count metadata) instead of polling multiplexer state.

And the *aggregate-approve* batch action absorbed from
``commands/babysit.py`` per spec §0.2 (issue #516 / L7):

- ``AggregateApprovalResult`` — approved/escalated counts + per-surface
  dispositions. Absorbed from babysit's ``AggregateApprovalResult``.
- ``cmd_aggregate_approve`` — enumerate agent dirs, classify pending
  prompts using shared bash patterns, write approval signals.

Output is at parity with ``atdd babysit`` at time of decommissioning,
modulo trailing whitespace. **This parity is a gating condition for
#P6 (babysit decommissioning).**

Subcommands per spec §5.4:
    run                — start the observer for an agent (tail + evaluate loop)
    attach             — print recent observations for an agent
    status             — surface dashboard (#515 / L6)
    aggregate-approve  — batch approval action (#516 / L7)

Out of scope:
- The 17 default detection rules (#L2-#L5).
- The babysit parity test suite (#L8).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from atdd.coach.utils.rule_binding import (
    AmbiguousRuleError,
    RuleNotInRegistryError,
    bind_rule,
)


# ---------------------------------------------------------------------------
# Frozen vocabulary (mirrors correction.schema.json)
# ---------------------------------------------------------------------------

INJECTION_METHODS: frozenset[str] = frozenset(
    {"cli-return", "multiplexer-send", "respawn"}
)

# #713 Layer 1: a co-spawned observer's agent_id is the persona's id plus
# this suffix (e.g. ``planner-42-ab-observer`` watches ``planner-42-ab``).
_OBSERVER_SUFFIX = "-observer"
DISPOSITIONS: frozenset[str] = frozenset(
    {"strict", "suppress-and-clean", "advisory", "documentation-only"}
)


def _now_iso_z() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _runtime_root(runtime_root: Optional[Path]) -> Path:
    if runtime_root is not None:
        return Path(runtime_root)
    env = os.environ.get("ATDD_RUNTIME_ROOT")
    if env:
        return Path(env)
    return Path.cwd() / ".atdd" / "runtime"


def _agent_dir(agent_id: str, runtime_root: Optional[Path]) -> Path:
    d = _runtime_root(runtime_root) / "agents" / agent_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _derive_persona_agent_id(agent_id: str) -> str:
    """The persona an observer watches: its agent_id minus the
    ``-observer`` suffix (#713 Layer 1).

    A bare id — the L1 generic per-agent watcher — has no suffix and
    watches that agent directly, so it is returned unchanged.
    """
    if agent_id.endswith(_OBSERVER_SUFFIX) and len(agent_id) > len(
        _OBSERVER_SUFFIX
    ):
        return agent_id[: -len(_OBSERVER_SUFFIX)]
    return agent_id


# ---------------------------------------------------------------------------
# Correction record
# ---------------------------------------------------------------------------


@dataclass
class Correction:
    """In-memory view of a correction.schema.json record."""

    agent_id: str
    rule_id: str
    severity: int
    disposition: str
    correction_text: str
    injection_method: str = "cli-return"
    issued_at: Optional[str] = None
    validator_id: Optional[str] = None
    violation_location: Optional[str] = None

    def to_record(self) -> dict:
        rec: dict = {
            "agent_id": self.agent_id,
            "rule_id": self.rule_id,
            "severity": int(self.severity),
            "disposition": self.disposition,
            "correction_text": self.correction_text,
            "injection_method": self.injection_method,
        }
        if self.issued_at:
            rec["issued_at"] = self.issued_at
        if self.validator_id:
            rec["validator_id"] = self.validator_id
        if self.violation_location:
            rec["violation_location"] = self.violation_location
        return rec


# ---------------------------------------------------------------------------
# Observed input (passed to rule predicates)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ObservedInput:
    """Snapshot of the agent's runtime state for one evaluation pass.

    Extra fields beyond the L1-skeleton baseline (``agent_id``,
    ``log_lines``, ``events``, ``worktree_changes``) carry the inputs the
    L2 basic-protocol rules need (issue #506). Each defaults so existing
    L1 callers stay backward-compatible.

    - ``now`` / ``last_token_at`` / ``heartbeat_mtime``: epoch seconds for
      the silence and heartbeat-staleness rules. ``None`` means
      "not-observed-yet" (rules treat as no-fire).
    - ``persona``: agent persona string (``"reviewer"``, ``"coder"``, …)
      used by the reviewer-edit-attempt rule.
    - ``wmbt_target_paths``: prefixes (relative to the worktree root)
      declared in scope by the WMBT — anything outside is out-of-scope.
    - ``prior_violations``: tuple of dicts, each carrying at minimum a
      ``rule_id`` key (and optionally ``sha``, ``fix_hint``). Sourced
      from a prior commit's ``validations/<sha>/violations.jsonl``.
    - ``addressed_rule_ids``: rule_ids the agent has addressed in the
      new commit (e.g. via fixed-up trailers / new code paths).
    """

    agent_id: str
    log_lines: tuple[str, ...] = ()
    events: tuple[dict, ...] = ()
    worktree_changes: tuple[str, ...] = ()
    now: Optional[float] = None
    last_token_at: Optional[float] = None
    heartbeat_mtime: Optional[float] = None
    persona: Optional[str] = None
    wmbt_target_paths: tuple[str, ...] = ()
    prior_violations: tuple[dict, ...] = ()
    addressed_rule_ids: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Observer rule
# ---------------------------------------------------------------------------


# A predicate may return either:
#   - bool          : ``True`` fires the rule (no correction-text formatting),
#                     ``False`` does not.
#   - dict          : truthy fire; the dict is passed as kwargs to
#                     ``correction_text.format(**dict)`` so rules can splice
#                     dynamic data (silence duration, offending path, etc.)
#                     into their correction text.
#   - None          : equivalent to ``False`` (no fire).
Predicate = Callable[[ObservedInput], Any]


class ObserverRule:
    """A loaded observer rule.

    The ``rule_id`` is resolved through ``bind_rule()`` at construction
    time. An unbindable id raises ``RuleNotInRegistryError`` (or
    ``AmbiguousRuleError``) and the registry surfaces this as a load
    error rather than crashing the observer.
    """

    def __init__(
        self,
        *,
        rule_id: str,
        predicate: Predicate,
        correction_text: str,
        injection_method: str = "cli-return",
        severity: int = 3,
        disposition: str = "advisory",
        source_path: Optional[Path] = None,
    ) -> None:
        if injection_method not in INJECTION_METHODS:
            raise ValueError(
                f"injection_method must be one of {sorted(INJECTION_METHODS)}, "
                f"got {injection_method!r}"
            )
        if disposition not in DISPOSITIONS:
            raise ValueError(
                f"disposition must be one of {sorted(DISPOSITIONS)}, "
                f"got {disposition!r}"
            )
        self.metadata = bind_rule(rule_id)
        self.rule_id = self.metadata.rule_id
        self.predicate = predicate
        self.correction_text = correction_text
        self.injection_method = injection_method
        self.severity = int(severity)
        self.disposition = disposition
        self.source_path = source_path

    def evaluate(self, ctx: ObservedInput, *, agent_id: str) -> Optional[Correction]:
        result = self.predicate(ctx)
        if not result:
            return None
        format_args = result if isinstance(result, dict) else {}
        try:
            text = self.correction_text.format(**format_args)
        except (KeyError, IndexError, ValueError):
            # Malformed template / missing key — emit the raw text rather
            # than crash the rule. Logged so the rule author can fix the
            # YAML.
            print(
                f"observer: rule {self.rule_id} correction_text formatting "
                f"failed; emitting raw template",
                file=sys.stderr,
            )
            text = self.correction_text
        return Correction(
            agent_id=agent_id,
            rule_id=self.rule_id,
            severity=self.severity,
            disposition=self.disposition,
            correction_text=text,
            injection_method=self.injection_method,
            issued_at=_now_iso_z(),
        )


# ---------------------------------------------------------------------------
# Rule loader
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleLoadError:
    path: Path
    reason: str


def _make_log_regex_predicate(
    pattern: str,
    exclude_pattern: Optional[str] = None,
) -> Predicate:
    """Fire when any log line matches ``pattern`` and (when set) no log
    line in the same window matches ``exclude_pattern``. The exclude
    semantic is what lets rule 01 ignore properly-formatted
    ``atdd agent ask`` invocations even when the surrounding text reads
    like a question."""
    import re

    rx = re.compile(pattern)
    exrx = re.compile(exclude_pattern) if exclude_pattern else None

    def predicate(ctx: ObservedInput) -> bool:
        if exrx is not None and any(exrx.search(line) for line in ctx.log_lines):
            return False
        return any(rx.search(line) for line in ctx.log_lines)

    return predicate


def _make_token_threshold_predicate() -> Predicate:
    def predicate(ctx: ObservedInput) -> bool:
        from atdd.coach.commands import token_threshold as _tt

        threshold = _tt.load_token_alert_threshold()
        count = _tt.read_token_count()
        return _tt.check_token_threshold(token_count=count, threshold=threshold)

    return predicate


def _make_token_silence_predicate(threshold_seconds: float) -> Predicate:
    """Fire when ``ctx.now - ctx.last_token_at > threshold_seconds``."""

    def predicate(ctx: ObservedInput):
        if ctx.now is None or ctx.last_token_at is None:
            return False
        elapsed = ctx.now - ctx.last_token_at
        if elapsed <= threshold_seconds:
            return False
        return {"duration_seconds": int(elapsed)}

    return predicate


def _make_completion_without_commit_predicate(
    completion_pattern: str,
) -> Predicate:
    """Fire when log lines contain a completion claim and no
    ``commit_observed`` event is present in ``ctx.events``."""
    import re

    rx = re.compile(completion_pattern, flags=re.IGNORECASE)

    def predicate(ctx: ObservedInput) -> bool:
        claimed = any(rx.search(line) for line in ctx.log_lines)
        if not claimed:
            return False
        committed = any(
            isinstance(e, dict) and e.get("type") == "commit_observed"
            for e in ctx.events
        )
        return not committed

    return predicate


def _make_out_of_scope_edit_predicate(
    *,
    atdd_allowlist_prefixes: tuple[str, ...] = (),
) -> Predicate:
    """Fire when any worktree change is either:
      (a) not under any of ``ctx.wmbt_target_paths`` (when target paths
          are declared); or
      (b) under ``.atdd/`` AND not under one of
          ``atdd_allowlist_prefixes`` (the absorbed babysit clause).

    Returns format-args naming the first offending path so the
    correction can identify it."""

    def _under_any(path: str, prefixes: tuple[str, ...]) -> bool:
        for prefix in prefixes:
            norm = prefix.rstrip("/")
            if norm in ("", "."):
                return True
            if path == norm or path.startswith(norm + "/"):
                return True
        return False

    def predicate(ctx: ObservedInput):
        for change in ctx.worktree_changes:
            # (b) the absorbed babysit `.atdd/` clause is enforced
            # independently of WMBT scope: any `.atdd/` write that isn't
            # under the allowlist fires regardless of the WMBT.
            if change.startswith(".atdd/") and not _under_any(
                change, atdd_allowlist_prefixes
            ):
                return {"path": change}
            # (a) WMBT scope check: only enforced when the WMBT declared
            # one or more target paths.
            if ctx.wmbt_target_paths and not _under_any(
                change, ctx.wmbt_target_paths
            ):
                return {"path": change}
        return False

    return predicate


def _make_heartbeat_stale_predicate(threshold_seconds: float) -> Predicate:
    """Fire when ``ctx.now - ctx.heartbeat_mtime > threshold_seconds``."""

    def predicate(ctx: ObservedInput):
        if ctx.now is None or ctx.heartbeat_mtime is None:
            return False
        age = ctx.now - ctx.heartbeat_mtime
        if age <= threshold_seconds:
            return False
        return {"age_seconds": int(age)}

    return predicate


def _make_reviewer_edit_attempt_predicate(
    *,
    persona: str = "reviewer",
    edit_pattern: str = r"\b(edit|commit|patch|diff|write)\b",
) -> Predicate:
    """Fire when ``ctx.persona == persona`` AND any log line matches
    ``edit_pattern``."""
    import re

    rx = re.compile(edit_pattern, flags=re.IGNORECASE)

    def predicate(ctx: ObservedInput) -> bool:
        if (ctx.persona or "").lower() != persona.lower():
            return False
        return any(rx.search(line) for line in ctx.log_lines)

    return predicate


def _make_validator_failure_ignored_predicate() -> Predicate:
    """Fire when ``ctx.prior_violations`` cites rule_ids that are not in
    ``ctx.addressed_rule_ids``. The format args carry the unaddressed
    rule_ids and their fix_hints (resolved via ``bind_rule()``)."""

    def predicate(ctx: ObservedInput):
        if not ctx.prior_violations:
            return False
        addressed = set(ctx.addressed_rule_ids)
        unaddressed: list[str] = []
        for v in ctx.prior_violations:
            if not isinstance(v, dict):
                continue
            rid = v.get("rule_id")
            if rid and rid not in addressed and rid not in unaddressed:
                unaddressed.append(rid)
        if not unaddressed:
            return False
        # Resolve fix_hints via bind_rule(); fall back to whatever the
        # prior-violation record carried locally if the rule_id isn't
        # registered in this repo's convention tree.
        lines: list[str] = []
        for rid in unaddressed:
            hint = None
            try:
                hint = bind_rule(rid).fix_hint
            except (RuleNotInRegistryError, AmbiguousRuleError):
                hint = None
            if hint is None:
                # Local fallback from the prior-violation record itself.
                for v in ctx.prior_violations:
                    if isinstance(v, dict) and v.get("rule_id") == rid:
                        hint = v.get("fix_hint")
                        break
            lines.append(f"  - {rid}: {hint or '(no fix_hint registered)'}")
        return {
            "unaddressed": ", ".join(unaddressed),
            "fix_hints_block": "\n".join(lines),
        }

    return predicate


def _resolve_python_callable(spec: str):
    """Resolve a ``module:attr`` spec to the referenced object.

    Used by the ``python`` trigger type so absorbed-from-babysit rules
    (#513) and future python-coded predicates can declare themselves in
    YAML without re-implementing their logic in regex.
    """
    if not isinstance(spec, str) or ":" not in spec:
        raise ValueError(
            f"python trigger 'callable' must be 'module:attr', got {spec!r}"
        )
    module_path, attr = spec.split(":", 1)
    import importlib

    module = importlib.import_module(module_path)
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ValueError(
            f"python trigger callable {spec!r} not found: {exc}"
        ) from exc


def _build_rule_from_yaml(payload: dict, *, source_path: Path) -> ObserverRule:
    if not isinstance(payload, dict):
        raise ValueError("rule YAML must be a mapping at the top level")

    trigger = payload.get("trigger") or {}
    if not isinstance(trigger, dict):
        raise ValueError("'trigger' must be a mapping")
    trig_type = trigger.get("type", "log_regex")

    # The 'python' trigger delegates rule construction to the referenced
    # module's ``build_rule()`` factory, which owns rule_id + predicate +
    # correction_text. The YAML file is purely a registry pointer.
    if trig_type == "python":
        builder_spec = trigger.get("builder")
        if not isinstance(builder_spec, str) or not builder_spec:
            raise ValueError("python trigger missing 'builder' (module:attr)")
        builder = _resolve_python_callable(builder_spec)
        rule = builder()
        if not isinstance(rule, ObserverRule):
            raise ValueError(
                f"python builder {builder_spec!r} must return ObserverRule, "
                f"got {type(rule).__name__}"
            )
        rule.source_path = source_path
        return rule

    rule_id = payload.get("rule_id")
    if not isinstance(rule_id, str) or not rule_id:
        raise ValueError("rule YAML missing required string field 'rule_id'")

    correction_text = payload.get("correction_text")
    if not isinstance(correction_text, str) or not correction_text:
        raise ValueError("rule YAML missing required string 'correction_text'")

    if trig_type == "log_regex":
        pattern = trigger.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError("log_regex trigger missing 'pattern'")
        predicate = _make_log_regex_predicate(
            pattern, exclude_pattern=trigger.get("exclude_pattern")
        )
    elif trig_type == "token_threshold":
        predicate = _make_token_threshold_predicate()
    elif trig_type == "token_silence":
        threshold = trigger.get("threshold_seconds")
        if not isinstance(threshold, (int, float)):
            raise ValueError("token_silence trigger missing numeric 'threshold_seconds'")
        predicate = _make_token_silence_predicate(float(threshold))
    elif trig_type == "completion_claim_without_commit":
        cp = trigger.get("completion_pattern")
        if not isinstance(cp, str) or not cp:
            raise ValueError(
                "completion_claim_without_commit trigger missing 'completion_pattern'"
            )
        predicate = _make_completion_without_commit_predicate(cp)
    elif trig_type == "out_of_scope_edit":
        allow = trigger.get("atdd_allowlist_prefixes") or ()
        if not isinstance(allow, (list, tuple)):
            raise ValueError("out_of_scope_edit 'atdd_allowlist_prefixes' must be a list")
        predicate = _make_out_of_scope_edit_predicate(
            atdd_allowlist_prefixes=tuple(allow),
        )
    elif trig_type == "heartbeat_stale":
        threshold = trigger.get("threshold_seconds")
        if not isinstance(threshold, (int, float)):
            raise ValueError("heartbeat_stale trigger missing numeric 'threshold_seconds'")
        predicate = _make_heartbeat_stale_predicate(float(threshold))
    elif trig_type == "reviewer_edit_attempt":
        predicate = _make_reviewer_edit_attempt_predicate(
            persona=trigger.get("persona", "reviewer"),
            edit_pattern=trigger.get(
                "edit_pattern", r"\b(edit|commit|patch|diff|write)\b"
            ),
        )
    elif trig_type == "validator_failure_ignored":
        predicate = _make_validator_failure_ignored_predicate()
    elif trig_type == "never":
        predicate = lambda _ctx: False  # noqa: E731 — terse intentional
    else:
        raise ValueError(
            f"unknown trigger.type {trig_type!r} (supported: log_regex, "
            f"token_threshold, token_silence, completion_claim_without_commit, "
            f"out_of_scope_edit, heartbeat_stale, reviewer_edit_attempt, "
            f"validator_failure_ignored, never)"
        )

    return ObserverRule(
        rule_id=rule_id,
        predicate=predicate,
        correction_text=correction_text,
        injection_method=payload.get("injection_method", "cli-return"),
        severity=int(payload.get("severity", 3)),
        disposition=payload.get("disposition", "advisory"),
        source_path=source_path,
    )


# ---------------------------------------------------------------------------
# Rule registry — discover, load, evaluate, isolate faults
# ---------------------------------------------------------------------------


class RuleRegistry:
    """Loads observer rules from a directory and evaluates them with
    per-rule fault isolation.

    - Loading is alphabetical (deterministic) but evaluation outcome
      MUST NOT depend on rule order.
    - A rule that raises an unhandled exception during ``evaluate()`` is
      caught, recorded in ``faulty_rules``, logged to stderr with its
      rule_id, and skipped on subsequent evaluations for the run.
    - A rule that fails to LOAD (malformed YAML, unbindable rule_id,
      missing fields) is captured in ``load_errors`` and surfaced via
      a one-time stderr warning AND a ``meta: rule_load_error`` record
      appended to ``corrections.jsonl``.
    """

    def __init__(self) -> None:
        self.rules: list[ObserverRule] = []
        self.load_errors: list[RuleLoadError] = []
        self.faulty_rules: set[str] = set()

    # --- loading ----------------------------------------------------------

    def load_dir(self, rules_dir: Path) -> None:
        if not rules_dir.exists():
            return
        for path in sorted(rules_dir.glob("*.yaml")):
            self._load_one(path)

    def _load_one(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
            payload = yaml.safe_load(text)
            rule = _build_rule_from_yaml(payload, source_path=path)
        except (  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01  # rule load errors are surfaced via stderr + corrections.jsonl meta record per AC-006
            yaml.YAMLError,
            ValueError,
            TypeError,
            RuleNotInRegistryError,
            AmbiguousRuleError,
        ) as exc:
            err = RuleLoadError(path=path, reason=f"{type(exc).__name__}: {exc}")
            self.load_errors.append(err)
            print(
                f"observer: failed to load rule {path}: {err.reason}",
                file=sys.stderr,
            )
            return
        self.rules.append(rule)

    def add_rule(self, rule: ObserverRule) -> None:
        """Programmatic insertion (tests, fixtures, future composition)."""
        self.rules.append(rule)

    # --- evaluation -------------------------------------------------------

    def evaluate(self, ctx: ObservedInput, *, agent_id: str) -> list[Correction]:
        out: list[Correction] = []
        for rule in self.rules:
            if rule.rule_id in self.faulty_rules:
                continue
            try:
                cor = rule.evaluate(ctx, agent_id=agent_id)
            except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01  # rule fault isolation per AC-004
                self.faulty_rules.add(rule.rule_id)
                print(
                    f"observer: rule {rule.rule_id} raised {type(exc).__name__}: "
                    f"{exc}; marked faulty for run",
                    file=sys.stderr,
                )
                continue
            if cor is not None:
                out.append(cor)
        return out


# ---------------------------------------------------------------------------
# Append-only writers
# ---------------------------------------------------------------------------


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True))
        fh.write("\n")


def append_correction(agent_dir: Path, correction: Correction) -> Path:
    path = agent_dir / "corrections.jsonl"
    _append_jsonl(path, correction.to_record())
    return path


def append_load_error(agent_dir: Path, error: RuleLoadError) -> Path:
    path = agent_dir / "corrections.jsonl"
    record = {
        "meta": "rule_load_error",
        "rule_path": str(error.path),
        "reason": error.reason,
        "issued_at": _now_iso_z(),
    }
    _append_jsonl(path, record)
    return path


# ---------------------------------------------------------------------------
# Injection dispatcher — three correction injection paths per spec §8.2
# ---------------------------------------------------------------------------


class InjectionDispatcher:
    """Routes a correction to one of three injection paths.

    Paths per spec §8.2:
        1. ``cli-return``       — write the correction text + rule_id to
           ``<agent_dir>/cli-return.jsonl`` so the agent's CLI return
           channel surfaces it on next read. Default path.
        2. ``multiplexer-send`` — call ``multiplexer.send(ref, text)`` to
           type the correction into the agent's terminal pane.
        3. ``respawn``          — invoke ``respawn_callback(agent_id, reason)``
           so coach can kill and respawn the agent process.
    """

    def __init__(
        self,
        *,
        multiplexer: Optional[Any] = None,
        multiplexer_ref_for_agent: Optional[Callable[[str], str]] = None,
        respawn_callback: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.multiplexer = multiplexer
        self.multiplexer_ref_for_agent = multiplexer_ref_for_agent or (
            lambda agent_id: f"surface:{agent_id}"
        )
        self.respawn_callback = respawn_callback

    def supported_methods(self) -> tuple[str, ...]:
        return ("cli-return", "multiplexer-send", "respawn")

    def dispatch(self, correction: Correction, *, agent_dir: Path) -> None:
        method = correction.injection_method
        if method == "cli-return":
            self._dispatch_cli_return(correction, agent_dir)
        elif method == "multiplexer-send":
            self._dispatch_multiplexer(correction)
        elif method == "respawn":
            self._dispatch_respawn(correction)
        else:
            raise ValueError(f"unsupported injection_method: {method!r}")

    def _dispatch_cli_return(self, correction: Correction, agent_dir: Path) -> None:
        record = {
            "rule_id": correction.rule_id,
            "correction_text": correction.correction_text,
            "severity": correction.severity,
            "issued_at": correction.issued_at or _now_iso_z(),
        }
        _append_jsonl(agent_dir / "cli-return.jsonl", record)

    def _dispatch_multiplexer(self, correction: Correction) -> None:
        if self.multiplexer is None:
            raise RuntimeError(
                "multiplexer-send dispatch requires a multiplexer backend; "
                "got None. Pass multiplexer=... to InjectionDispatcher."
            )
        ref = self.multiplexer_ref_for_agent(correction.agent_id)
        self.multiplexer.send(ref, correction.correction_text)

    def _dispatch_respawn(self, correction: Correction) -> None:
        if self.respawn_callback is None:
            raise RuntimeError(
                "respawn dispatch requires a respawn_callback; got None."
            )
        self.respawn_callback(correction.agent_id, correction.correction_text)


# ---------------------------------------------------------------------------
# Observer — main loop
# ---------------------------------------------------------------------------


class Observer:
    """Per-agent detect-and-correct sidecar.

    Public surface:
        load_rules()      — discover and load rules from ``rules_dir``
        collect_input()   — read new lines from ``output.log`` and detect
                            worktree changes; returns an ``ObservedInput``
        scan_once()       — collect input, evaluate registry, persist
                            corrections, dispatch via the injection paths
        start()/stop()    — daemon mode (background thread, polling)
    """

    def __init__(
        self,
        *,
        agent_id: str,
        runtime_dir: Path,
        rules_dir: Optional[Path],
        worktree: Optional[Path] = None,
        dispatcher: Optional[InjectionDispatcher] = None,
        poll_interval: float = 0.5,
        surface_capture: Optional[Callable[[], str]] = None,
        ask_idle_seconds: float = 600.0,
        escalate_idle_seconds: float = 1800.0,
    ) -> None:
        self.agent_id = agent_id
        self.runtime_dir = Path(runtime_dir)
        self.rules_dir = Path(rules_dir) if rules_dir else None
        self.worktree = Path(worktree) if worktree else None
        self.agent_dir = self.runtime_dir / "agents" / agent_id
        self.agent_dir.mkdir(parents=True, exist_ok=True)
        # #713 Layer 1: collect_input must read the PERSONA's runtime dir,
        # not the observer's own.
        self.persona_agent_id = _derive_persona_agent_id(agent_id)
        self.persona_dir = self.runtime_dir / "agents" / self.persona_agent_id
        self.surface_capture = surface_capture
        self.registry = RuleRegistry()
        self.dispatcher = dispatcher or InjectionDispatcher()
        self.poll_interval = poll_interval
        self._log_offset = 0
        # #713 Layer 4: live observability state for the operator status line.
        self.last_input: Optional[ObservedInput] = None
        self.last_corrections: list[Correction] = []
        self.last_scan_at: Optional[float] = None
        self.corrections_issued = 0
        self._worktree_snapshot: dict[str, float] = {}
        self._worktree_baseline_taken = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # #731 Phase 2: worker->coach event loop. The observer — a per-worker
        # LLM-neutral sidecar — emits the worker's heartbeat/ask/escalate
        # itself, because the worker LLM cannot be relied on to emit them.
        self._ask_idle_seconds = ask_idle_seconds
        self._escalate_idle_seconds = escalate_idle_seconds
        # De-dup: emit ask/escalate once per blocked episode, not every poll.
        self._block_signalled = False
        # Roots excluded from worktree scanning (#706). The observer writes
        # its own corrections.jsonl / cli-return.jsonl into runtime_dir,
        # which lives INSIDE the scanned worktree — scanning it makes every
        # correction-write a detected change, which fires out-of-scope-edit,
        # which writes another correction: an unbounded self-feedback loop.
        # Exclude the observer's own runtime tree (resolved relative to the
        # worktree when given as a relative path).
        self._scan_skip_roots: list[Path] = []
        if self.worktree is not None:
            rt = self.runtime_dir
            if not rt.is_absolute():
                rt = self.worktree / rt
            try:
                self._scan_skip_roots.append(rt.resolve())
            except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
                pass

    # --- rule loading -----------------------------------------------------

    def load_rules(self) -> None:
        if self.rules_dir is not None:
            self.registry.load_dir(self.rules_dir)
        for err in self.registry.load_errors:
            append_load_error(self.agent_dir, err)

    # --- input collection -------------------------------------------------

    def collect_input(self) -> ObservedInput:
        # #713 Layer 3: acquire the persona output stream before tailing.
        self._acquire_surface()
        # #713 Layer 2: populate now / last_token_at / heartbeat_mtime so
        # the silence (02) and missed-heartbeat (05) predicates evaluate
        # instead of short-circuiting on None.
        return ObservedInput(
            agent_id=self.agent_id,
            log_lines=tuple(self._tail_output_log()),
            events=(),
            worktree_changes=tuple(self._scan_worktree()),
            now=time.time(),
            last_token_at=self._persona_file_mtime("output.log"),
            heartbeat_mtime=self._persona_file_mtime("heartbeat.json"),
        )

    def _acquire_surface(self) -> None:
        """#713 Layer 3 — acquire the persona's output stream.

        Planner decision (P002): the co-spawned observer captures the
        persona's multiplexer surface (``cmux capture-pane`` via the
        injected ``surface_capture`` callable) and tails the delta into
        the persona's ``output.log`` so the log-regex rules see real
        agent output.
        """
        if self.surface_capture is None:
            return
        try:
            captured = self.surface_capture()
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01  # surface capture is best-effort; failure is logged, not fatal
            print(f"observer: surface capture failed: {exc}", file=sys.stderr)
            return
        if not captured:
            return
        self.persona_dir.mkdir(parents=True, exist_ok=True)
        with (self.persona_dir / "output.log").open(
            "a", encoding="utf-8"
        ) as fh:
            fh.write(captured if captured.endswith("\n") else captured + "\n")

    def _persona_file_mtime(self, filename: str) -> Optional[float]:
        """mtime of a file in the persona's runtime dir, or None when
        absent — feeds the time/token fields the silence (02) and
        missed-heartbeat (05) predicates need (#713 Layer 2)."""
        path = self.persona_dir / filename
        if not path.exists():
            return None
        return path.stat().st_mtime

    def _tail_output_log(self) -> list[str]:
        # #713 Layer 1: read the PERSONA's output.log, not the observer's.
        log_path = self.persona_dir / "output.log"
        if not log_path.exists():
            return []
        size = log_path.stat().st_size
        if size < self._log_offset:
            self._log_offset = 0
        if size == self._log_offset:
            return []
        with log_path.open("r", encoding="utf-8", errors="replace") as fh:
            fh.seek(self._log_offset)
            chunk = fh.read()
            self._log_offset = fh.tell()
        lines = chunk.splitlines()
        return [ln for ln in lines if ln]

    # Directory components whose subtrees carry no agent work — pruned from
    # every worktree scan (#706): VCS internals and Python bytecode caches.
    _SCAN_SKIP_PARTS = frozenset({".git", "__pycache__"})

    def _is_excluded_from_scan(self, path: Path) -> bool:
        """True when *path* is the observer's own runtime output or VCS/cache
        noise — excluding it breaks the self-feedback loop (#706)."""
        if any(part in self._SCAN_SKIP_PARTS for part in path.parts):
            return True
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        return any(
            resolved.is_relative_to(root) for root in self._scan_skip_roots
        )

    def _scan_worktree(self) -> list[str]:
        if self.worktree is None or not self.worktree.exists():
            return []
        current: dict[str, float] = {}
        for p in self.worktree.rglob("*"):
            if p.is_file() and not self._is_excluded_from_scan(p):
                try:
                    rel = str(p.relative_to(self.worktree))
                except ValueError:
                    continue
                current[rel] = p.stat().st_mtime
        if not self._worktree_baseline_taken:
            self._worktree_snapshot = current
            self._worktree_baseline_taken = True
            return []
        changed: list[str] = []
        for path, mtime in current.items():
            prev = self._worktree_snapshot.get(path)
            if prev is None or prev != mtime:
                changed.append(path)
        for path in self._worktree_snapshot:
            if path not in current:
                changed.append(path)
        self._worktree_snapshot = current
        return sorted(changed)

    # --- evaluation pass --------------------------------------------------

    def scan_once(self) -> list[Correction]:
        ctx = self.collect_input()
        self.last_input = ctx
        self.last_scan_at = time.time()
        # #731 Phase 2/3: drive the worker->coach event loop — emit the
        # worker's heartbeat and surface a blocked worker as ask/escalate.
        # Advisory: a failure here must never block rule evaluation.
        try:
            self._run_worker_event_loop(ctx)
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31  # event-loop emission is advisory; failure must not block corrections
            print(
                f"observer: worker event loop raised {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
        corrections = self.registry.evaluate(ctx, agent_id=self.agent_id)
        self.last_corrections = list(corrections)
        self.corrections_issued += len(corrections)
        for cor in corrections:
            append_correction(self.agent_dir, cor)
            try:
                self.dispatcher.dispatch(cor, agent_dir=self.agent_dir)
            except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01  # injection failures are advisory in skeleton
                print(
                    f"observer: injection failed for {cor.rule_id}: {exc}",
                    file=sys.stderr,
                )
        return corrections

    # --- worker -> coach event loop (#731 Phase 2/3) ----------------------

    # A line that signals the worker is awaiting a decision (not merely
    # quiet). Tuned to fire on real decision/block language but stay silent
    # on neutral progress text.
    _DECISION_MARKER = re.compile(
        r"(?i)(\bdecision\b|\bblocked\b|cannot proceed|\bawaiting\b"
        r"|need\b.{0,16}\banswer\b|should i\b|\?)"
    )

    @staticmethod
    def _agent_module():
        """Lazy import — the worker->coach event loop emits through the same
        ``atdd agent`` primitives a worker would, keeping the path LLM-neutral
        and adapter-agnostic."""
        from atdd.coach.commands import agent

        return agent

    def _run_worker_event_loop(self, ctx: "ObservedInput") -> None:
        self._emit_worker_heartbeat()
        self._evaluate_worker_block(ctx)

    def _emit_worker_heartbeat(self) -> None:
        """Emit one ``heartbeat`` event for the worker so the coach sees
        liveness. The worker LLM does not emit these itself (#731)."""
        self._agent_module().cmd_event(
            "heartbeat",
            agent_id=self.persona_agent_id,
            data={"emitted_by": self.agent_id, "source": "observer"},
            runtime_root=self.runtime_dir,
        )

    def _has_decision_marker(self, ctx: "ObservedInput") -> bool:
        return any(self._DECISION_MARKER.search(line) for line in ctx.log_lines)

    def detect_blocked_worker(self, ctx: "ObservedInput") -> list[str]:
        """Classify the worker's idle state. Returns any of ``"ask"`` /
        ``"escalate"`` — empty when the worker is progressing.

        ``ask``      — idle past the ask threshold AND the recent output
                       shows the worker awaiting a decision.
        ``escalate`` — idle past the (longer) escalation threshold,
                       regardless of decision language: a hard block.
        """
        last = ctx.last_token_at
        if last is None:
            return []  # no output stream yet — not started, not blocked
        idle = ctx.now - last
        signals: list[str] = []
        if idle >= self._ask_idle_seconds and self._has_decision_marker(ctx):
            signals.append("ask")
        if idle >= self._escalate_idle_seconds:
            signals.append("escalate")
        return signals

    def _evaluate_worker_block(self, ctx: "ObservedInput") -> None:
        signals = self.detect_blocked_worker(ctx)
        if not signals:
            # Worker is progressing — reset so the next block re-signals.
            self._block_signalled = False
            return
        if self._block_signalled:
            return  # already signalled this blocked episode — no spam
        agent = self._agent_module()
        idle = ctx.now - (ctx.last_token_at or ctx.now)
        if "ask" in signals:
            agent.cmd_ask(
                question=self._decision_context(ctx),
                type="text",
                agent_id=self.persona_agent_id,
                runtime_root=self.runtime_dir,
            )
        if "escalate" in signals:
            agent.cmd_escalate(
                reason=(
                    f"worker idle {idle:.0f}s with no output — hard-blocked "
                    f"(observer-detected, {self.agent_id})"
                ),
                severity="block",
                agent_id=self.persona_agent_id,
                runtime_root=self.runtime_dir,
            )
        self._block_signalled = True

    def _decision_context(self, ctx: "ObservedInput") -> str:
        """The captured decision the worker is stalled on — the last output
        line carrying decision language, or a generic fallback."""
        for line in reversed(ctx.log_lines):
            if self._DECISION_MARKER.search(line):
                return line.strip()
        return "worker appears blocked awaiting a decision"

    def deliver_answer(self, question_id: str, answer: str) -> Path:
        """Round-trip a coach/operator answer back into the worker (#731
        Phase 3).

        The answer is written to ``<worker>/answers/<question_id>.json`` —
        exactly where ``agent.read_answer`` reads it — so the worker can
        pick it up and unblock. Adapter-neutral: it uses the generic
        runtime tree, no Claude-Code-specific hook.
        """
        answers_dir = self.persona_dir / "answers"
        answers_dir.mkdir(parents=True, exist_ok=True)
        target = answers_dir / f"{question_id}.json"
        record = {
            "question_id": question_id,
            "answer": answer,
            "delivered_at": _now_iso_z(),
            "delivered_by": self.agent_id,
        }
        target.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        # A delivered answer resolves the current blocked episode.
        self._block_signalled = False
        return target

    # --- daemon mode ------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="observer", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01  # daemon must never crash on a single pass
                print(
                    f"observer: scan_once raised {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
            self._stop.wait(self.poll_interval)


# ---------------------------------------------------------------------------
# Operator observability (#713 Layer 4 — OBSINPUT-005 / OBSINPUT-006)
# ---------------------------------------------------------------------------


def render_status_line(observer: "Observer") -> str:
    """The one operator-interpretable observer status line.

    The single shared mechanism every observer-bearing entry point uses
    so no observer tab is headless — universal operator-visibility per
    issue #713 (OBSINPUT-005 / OBSINPUT-006).
    """
    if observer.last_scan_at is None:
        last_scan = "pending"
    else:
        last_scan = (
            datetime.fromtimestamp(observer.last_scan_at, timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    return (
        f"observer | watching {observer.persona_agent_id} "
        f"| {len(observer.registry.rules)} rules loaded "
        f"| last scan {last_scan} "
        f"| {observer.corrections_issued} corrections issued"
    )


def _emit_observer_status(observer: "Observer") -> None:
    """Print the status line plus the last scan's ingest+fired trace so
    the operator can see what the observer evaluated and which rules
    fired. Reads the observer's recorded last-scan state."""
    print(render_status_line(observer))
    if observer.last_input is not None:
        for line in observer.last_input.log_lines:
            print(f"  ingested: {line}")
    for cor in observer.last_corrections:
        print(f"  fired: {cor.rule_id}")


# ---------------------------------------------------------------------------
# Persona heartbeat producer (#713 scope item 2 — P002-INTEGRATION-001)
# ---------------------------------------------------------------------------


class _HeartbeatTicker:
    """Refreshes ``<agent_dir>/heartbeat.json`` on a timer.

    Co-spawned beside a persona so rule 05 (missed-heartbeat) has a live
    liveness signal — a running Claude persona does not emit heartbeats
    on its own.
    """

    def __init__(self, agent_dir: Path, interval: float) -> None:
        self.agent_dir = Path(agent_dir)
        self.interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, name="heartbeat", daemon=True
        )

    def start(self) -> "_HeartbeatTicker":
        self._thread.start()
        return self

    def _write(self) -> None:
        self.agent_dir.mkdir(parents=True, exist_ok=True)
        (self.agent_dir / "heartbeat.json").write_text(
            json.dumps({"ts": _now_iso_z(), "pid": os.getpid()}),
            encoding="utf-8",
        )

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._write()
            self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)


def start_heartbeat_ticker(
    *, agent_dir: Path, interval: float = 30.0
) -> _HeartbeatTicker:
    """Start a heartbeat producer beside the persona. Returns a handle
    with ``.stop()``."""
    return _HeartbeatTicker(agent_dir, interval).start()


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------


def cmd_run(
    *,
    agent_id: str,
    runtime_dir: Optional[Path] = None,
    rules_dir: Optional[Path] = None,
    worktree: Optional[Path] = None,
    once: bool = False,
    poll_interval: float = 0.5,
    multiplexer: Optional[Any] = None,
    respawn_callback: Optional[Callable[[str, str], None]] = None,
) -> int:
    runtime = _runtime_root(runtime_dir)
    if rules_dir is None:
        rules_dir = Path.cwd() / ".atdd" / "observer" / "rules"
    dispatcher = InjectionDispatcher(
        multiplexer=multiplexer,
        respawn_callback=respawn_callback,
    )
    obs = Observer(
        agent_id=agent_id,
        runtime_dir=runtime,
        rules_dir=rules_dir,
        worktree=worktree,
        dispatcher=dispatcher,
        poll_interval=poll_interval,
    )
    obs.load_rules()
    if once:
        obs.scan_once()
        _emit_observer_status(obs)
        return 0
    obs.start()
    try:
        while True:
            time.sleep(0.5)
            # #713 Layer 4: keep the observer tab interpretable — never a
            # blank surface after launch.
            print(render_status_line(obs))
    except KeyboardInterrupt:
        obs.stop()
    return 0


def cmd_attach(
    *,
    agent_id: str,
    runtime_dir: Optional[Path] = None,
    limit: int = 20,
) -> int:
    runtime = _runtime_root(runtime_dir)
    agent_dir = runtime / "agents" / agent_id
    cor_path = agent_dir / "corrections.jsonl"
    if not cor_path.exists():
        print(f"observer: no corrections recorded for {agent_id}", file=sys.stderr)
        return 0
    raw_lines = cor_path.read_text(encoding="utf-8").splitlines()
    tail = raw_lines[-limit:] if limit and limit > 0 else raw_lines
    for raw in tail:
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if rec.get("meta") == "rule_load_error":
            print(
                f"[rule_load_error] {rec.get('rule_path', '<no-path>')}: "
                f"{rec.get('reason', '')}"
            )
            continue
        ts = rec.get("issued_at", "<no-ts>")
        rule_id = rec.get("rule_id", "<no-id>")
        text = rec.get("correction_text", "")
        print(f"{ts}  {rule_id}  {text}")
    return 0


# ---------------------------------------------------------------------------
# Dashboard primitives — absorbed from `commands/babysit.py` per spec §0.2
# (issue #515 / L6). Output parity with babysit modulo trailing whitespace
# is a gating condition for #P6 (babysit decommissioning).
# ---------------------------------------------------------------------------


@dataclass
class SurfaceRow:
    """One rendered row of the dashboard. Pure data."""

    ref: str
    issue: Optional[int]
    phase: str
    last_tool_seconds: float
    pending_prompt: str  # "" or "1 (Bash)" — recomputed each cycle
    stalled: bool
    status: str  # ACTIVE | STALLED | escalated | violation
    # New for L6: optional token-count surfacing per AC-001. Not rendered
    # in the legacy column layout (parity with babysit), but carried on
    # the row so downstream consumers can read it.
    token_count: Optional[int] = None


def _format_hms(seconds: float) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}"


def _render_dashboard(
    *,
    rows: list,
    now_iso: str,
    scope_label: str,
) -> str:
    """Render the aggregate table as a single string. Pure.

    Layout is preserved verbatim from ``babysit._render_dashboard`` to
    guarantee output parity at decommissioning (AC-002 / #P6 gate).
    """
    header = (
        f"ATDD Dashboard — {scope_label} ({len(rows)} surface(s), "
        f"refreshed {now_iso})"
    )
    sep = "─" * 78
    columns = (
        f"{'Surface':<14}{'Issue':<10}{'Phase':<10}"
        f"{'LastTool':<11}{'PendingPrompts':<18}{'Status'}"
    )
    body_lines: list[str] = []
    for row in rows:
        issue_str = f"#{row.issue}" if row.issue is not None else "—"
        last_tool = _format_hms(row.last_tool_seconds)
        pending = row.pending_prompt or "0"
        body_lines.append(
            f"{row.ref:<14}{issue_str:<10}{row.phase:<10}"
            f"{last_tool:<11}{pending:<18}{row.status}"
        )
    return "\n".join([header, sep, columns, sep, *body_lines, sep])


# ---------------------------------------------------------------------------
# Runtime-folder data source — `.atdd/runtime/agents/<id>/`
# (issue #515 / L6). Replaces babysit's multiplexer polling.
# ---------------------------------------------------------------------------


_DEFAULT_STALE_WARN_MINUTES = 15


def _parse_iso_z_to_epoch(value: object) -> Optional[float]:
    """Parse an ISO-8601 ``observed_at`` / ``timestamp`` string into a
    POSIX timestamp. Accepts both ``...Z`` and ``...+00:00`` forms.
    Returns ``None`` for missing / unparseable inputs so the dashboard
    falls back to ``0:00:00`` rather than crashing the loop.
    """
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01  # malformed heartbeat ts → render 0:00:00 per spec §3.2 fallback
        return None


def _extract_surface_state_from_runtime(
    *,
    agent_dir: Path,
    now: Optional[float] = None,
    stale_warn_minutes: int = _DEFAULT_STALE_WARN_MINUTES,
) -> SurfaceRow:
    """Build a ``SurfaceRow`` from ``.atdd/runtime/agents/<id>/``.

    Reads ``heartbeat.json`` (last-known wall-clock + optional
    ``token_count``) and ``context.json`` (current ``phase`` and
    ``issue``). Pure-ish: only file I/O on the per-agent directory; no
    multiplexer / network calls.
    """
    if now is None:
        now = time.time()
    agent_id = agent_dir.name

    phase = "?"
    issue: Optional[int] = None
    context_path = agent_dir / "context.json"
    if context_path.is_file():
        try:
            ctx = json.loads(context_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01  # render `?` placeholder per AC-001 fallback
            print(
                f"observer: failed to read {context_path}: {exc}",
                file=sys.stderr,
            )
            ctx = {}
        if isinstance(ctx, dict):
            raw_phase = ctx.get("phase")
            if isinstance(raw_phase, str) and raw_phase:
                phase = raw_phase.upper()
            raw_issue = ctx.get("issue")
            if isinstance(raw_issue, int):
                issue = raw_issue
            elif isinstance(raw_issue, str) and raw_issue.isdigit():
                issue = int(raw_issue)

    last_tool_seconds = 0.0
    token_count: Optional[int] = None
    heartbeat_path = agent_dir / "heartbeat.json"
    if heartbeat_path.is_file():
        try:
            hb = json.loads(heartbeat_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01  # render 0:00:00 per spec §3.2 fallback
            print(
                f"observer: failed to read {heartbeat_path}: {exc}",
                file=sys.stderr,
            )
            hb = {}
        if isinstance(hb, dict):
            ts = _parse_iso_z_to_epoch(hb.get("observed_at") or hb.get("timestamp"))
            if ts is not None:
                last_tool_seconds = max(0.0, now - ts)
            raw_tokens = hb.get("token_count")
            if isinstance(raw_tokens, int) and raw_tokens >= 0:
                token_count = raw_tokens

    stalled = last_tool_seconds >= stale_warn_minutes * 60
    status = "STALLED" if stalled else "ACTIVE"

    return SurfaceRow(
        ref=agent_id,
        issue=issue,
        phase=phase,
        last_tool_seconds=last_tool_seconds,
        pending_prompt="",
        stalled=stalled,
        status=status,
        token_count=token_count,
    )


def cmd_status(*, runtime_dir: Optional[Path] = None) -> int:
    """`atdd observer status` — render the surface dashboard at parity
    with ``atdd babysit`` (issue #515 / L6).

    Data source is ``.atdd/runtime/agents/*/`` — no multiplexer polling.
    Output parity with babysit gates #P6 (babysit decommissioning).
    """
    runtime = _runtime_root(runtime_dir)
    agents_dir = runtime / "agents"
    rows: list[SurfaceRow] = []
    if agents_dir.exists():
        now = time.time()
        for child in sorted(agents_dir.iterdir()):
            if child.is_dir():
                rows.append(
                    _extract_surface_state_from_runtime(agent_dir=child, now=now)
                )
    now_iso = (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    output = _render_dashboard(
        rows=rows,
        now_iso=now_iso,
        scope_label=".atdd/runtime/agents/",
    )
    print(output)
    return 0


# ---------------------------------------------------------------------------
# Aggregate approval — absorbed from `commands/babysit.py` per spec §0.2
# (issue #516 / L7). Output parity with babysit gates #P6.
# ---------------------------------------------------------------------------


@dataclass
class AggregateApprovalResult:
    """Summary returned by `cmd_aggregate_approve`."""

    approved: int = 0
    escalated: int = 0
    approvals_by_ref: dict[str, str] = field(default_factory=dict)
    escalations_by_ref: dict[str, str] = field(default_factory=dict)


_PROMPT_MARKERS_OBSERVER: tuple[str, ...] = (
    "Do you want to proceed?",
    "Approve this tool use?",
    "❯ 1. Yes",
    "1) Yes, approve",
)


def _contains_prompt_marker(text: str) -> bool:
    return any(m in text for m in _PROMPT_MARKERS_OBSERVER)


def cmd_aggregate_approve(
    *,
    runtime_dir: Optional[Path] = None,
    scope: Optional[str] = None,
) -> AggregateApprovalResult:
    """`atdd observer aggregate-approve [--scope <ids>]` — batch-approve
    known-safe prompts across active sessions.

    Enumerates agent dirs from ``.atdd/runtime/agents/*/``, reads
    ``output.log`` for pending prompts, classifies using the same bash
    patterns as babysit (from ``orchestration.convention.yaml``), and
    writes approval signals to ``cli-return.jsonl``. Returns an
    ``AggregateApprovalResult`` with approved/escalated counts and
    per-surface dispositions.
    """
    # Lazy import to break the observer ↔ babysit circular dependency
    # (babysit imports SurfaceRow from observer).
    from atdd.coach.commands.babysit import (
        classify_prompt,
        detect_violation,
    )
    runtime = _runtime_root(runtime_dir)
    agents_dir = runtime / "agents"
    result = AggregateApprovalResult()

    # Parse --scope into a set of issue IDs.
    scope_ids: Optional[set[int]] = None
    if scope:
        scope_ids = set()
        for part in scope.split(","):
            part = part.strip()
            if part.isdigit():
                scope_ids.add(int(part))

    if not agents_dir.exists():
        return result

    for agent_child in sorted(agents_dir.iterdir()):
        if not agent_child.is_dir():
            continue

        agent_id = agent_child.name

        # Scope filter: if --scope is set, only include agents whose
        # context.json maps to an issue in scope.
        if scope_ids is not None:
            context_path = agent_child / "context.json"
            if not context_path.is_file():
                continue
            try:
                ctx = json.loads(context_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01  # scope filter: skip unparseable context per AC-001 fallback
                print(
                    f"observer: aggregate-approve: skipping {agent_id}: "
                    f"unreadable context.json",
                    file=sys.stderr,
                )
                continue
            issue = ctx.get("issue") if isinstance(ctx, dict) else None
            if issue is None or int(issue) not in scope_ids:
                continue

        # Read output.log tail for the prompt screen.
        output_log = agent_child / "output.log"
        if not output_log.is_file():
            continue
        try:
            screen = output_log.read_text(encoding="utf-8", errors="replace")
        except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01  # unreadable log → skip this surface per AC-001 fallback
            print(
                f"observer: aggregate-approve: skipping {agent_id}: "
                f"unreadable output.log",
                file=sys.stderr,
            )
            continue

        if not _contains_prompt_marker(screen):
            continue

        # Check for violations first (same order as babysit).
        violation = detect_violation(screen)
        if violation is not None:
            result.escalated += 1
            result.escalations_by_ref[agent_id] = violation.reason or "violation"
            continue

        # Classify using the shared babysit classifier (same bash patterns).
        decision = classify_prompt(screen)

        if decision.action == "auto_approve":
            # Write approval signal to cli-return.jsonl.
            approval_record = {
                "action": "auto_approve",
                "rule_id": decision.rule_id or "",
                "matched": decision.matched or "",
                "issued_at": _now_iso_z(),
            }
            _append_jsonl(agent_child / "cli-return.jsonl", approval_record)

            # Log the aggregate-approve event.
            _append_jsonl(
                agent_child / "corrections.jsonl",
                {
                    "event": "agg_approve",
                    "agent_id": agent_id,
                    "matched": decision.matched or "",
                    "pattern": decision.rule_id or "",
                    "reason": f"agg-approve: {decision.matched or 'auto'}",
                    "issued_at": _now_iso_z(),
                },
            )

            result.approved += 1
            result.approvals_by_ref[agent_id] = decision.rule_id or "auto"
        elif decision.action == "escalate":
            result.escalated += 1
            result.escalations_by_ref[agent_id] = decision.reason or "escalate"
        # idle → no-op

    return result


# ---------------------------------------------------------------------------
# argparse dispatcher
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd observer",
        description=(
            "Coach v9 detect-and-correct sidecar (issue #500). Subcommands: "
            "run / attach / status / aggregate-approve."
        ),
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    run_p = sub.add_parser("run", help="Tail an agent and dispatch corrections")
    run_p.add_argument("--agent-id", required=True)
    run_p.add_argument("--runtime-dir", default=None)
    run_p.add_argument("--rules-dir", default=None)
    run_p.add_argument("--worktree", default=None)
    run_p.add_argument("--once", action="store_true", help="Single pass then exit")
    run_p.add_argument("--poll-interval", type=float, default=0.5)

    attach_p = sub.add_parser("attach", help="Print recent corrections for an agent")
    attach_p.add_argument("--agent-id", required=True)
    attach_p.add_argument("--runtime-dir", default=None)
    attach_p.add_argument("--limit", type=int, default=20)

    status_p = sub.add_parser("status", help="Stub — body in #L6")
    status_p.add_argument("--runtime-dir", default=None)

    agg_p = sub.add_parser("aggregate-approve", help="Batch-approve known-safe prompts")
    agg_p.add_argument("--runtime-dir", default=None)
    agg_p.add_argument("--scope", default=None, help="Comma-separated issue IDs to scope to")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    runtime = Path(args.runtime_dir) if getattr(args, "runtime_dir", None) else None
    if args.subcommand == "run":
        rules = Path(args.rules_dir) if args.rules_dir else None
        worktree = Path(args.worktree) if args.worktree else None
        return cmd_run(
            agent_id=args.agent_id,
            runtime_dir=runtime,
            rules_dir=rules,
            worktree=worktree,
            once=args.once,
            poll_interval=args.poll_interval,
        )
    if args.subcommand == "attach":
        return cmd_attach(
            agent_id=args.agent_id,
            runtime_dir=runtime,
            limit=args.limit,
        )
    if args.subcommand == "status":
        return cmd_status(runtime_dir=runtime)
    if args.subcommand == "aggregate-approve":
        result = cmd_aggregate_approve(
            runtime_dir=runtime,
            scope=getattr(args, "scope", None),
        )
        print(f"{result.approved} prompts auto-approved")
        print(f"{result.escalated} prompts escalated (kept for manual review)")
        return 0
    parser.error(f"unknown subcommand {args.subcommand!r}")
    return 2


def run(argv: list[str]) -> int:
    return main(argv)


# ---------------------------------------------------------------------------
# Single coach-level multi-agent observer (issue #754 / E002)
# ---------------------------------------------------------------------------

#: Minimum poll interval enforced by MultiAgentObserver.
#: The observer must not busy-wait — 1.0s is the floor; default is 2.0s.
MULTI_OBSERVER_MIN_INTERVAL: float = 1.0


class MultiAgentObserver:
    """Single observer per coach that watches all active worker runtime dirs.

    Replaces N per-worker observer processes with one debounced scan loop.
    The loop discovers agent dirs under ``runtime_root/agents/*``, creates
    a lightweight per-agent :class:`Observer` on first sight, calls
    ``scan_once()`` for each, then sleeps for ``poll_interval`` seconds.

    ``poll_interval`` is clamped to :data:`MULTI_OBSERVER_MIN_INTERVAL` so
    the loop can never busy-wait.
    """

    def __init__(
        self,
        runtime_root: Path,
        *,
        rules_dir: Optional[Path] = None,
        poll_interval: float = 2.0,
    ) -> None:
        self.runtime_root = Path(runtime_root)
        self.rules_dir = rules_dir
        self.poll_interval = max(MULTI_OBSERVER_MIN_INTERVAL, poll_interval)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._per_agent: dict[str, Observer] = {}

    def start(self) -> "MultiAgentObserver":
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="coach-observer",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def _discover_agents(self) -> list[str]:
        agents_dir = self.runtime_root / "agents"
        if not agents_dir.exists():
            return []
        return [d.name for d in agents_dir.iterdir() if d.is_dir()]

    def _loop_once(self) -> None:
        """Run a single scan pass over all discovered agent dirs."""
        for agent_id in self._discover_agents():
            if agent_id not in self._per_agent:
                obs = Observer(
                    agent_id=agent_id,
                    runtime_dir=self.runtime_root,
                    rules_dir=self.rules_dir,
                )
                obs.load_rules()
                self._per_agent[agent_id] = obs
            try:
                self._per_agent[agent_id].scan_once()
            except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-14
                pass

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._loop_once()
            self._stop.wait(self.poll_interval)
