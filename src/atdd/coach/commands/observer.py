"""`atdd observer <subcommand>` — coach v9 observer (issues #500 + #515).

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

Output is at parity with ``atdd babysit``'s dashboard at time of
decommissioning, modulo trailing whitespace. **This parity is a
gating condition for #P6 (babysit decommissioning).**

Subcommands per spec §5.4:
    run                — start the observer for an agent (tail + evaluate loop)
    attach             — print recent observations for an agent
    status             — surface dashboard (#515 / L6)
    aggregate-approve  — batch approval action (stub here; full body in #L7)

Out of scope:
- The 17 default detection rules (#L2-#L5).
- The ``aggregate-approve`` action body (#L7).
- The babysit parity test suite (#L8).
"""
from __future__ import annotations

import argparse
import json
import os
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


def _build_rule_from_yaml(payload: dict, *, source_path: Path) -> ObserverRule:
    if not isinstance(payload, dict):
        raise ValueError("rule YAML must be a mapping at the top level")
    rule_id = payload.get("rule_id")
    if not isinstance(rule_id, str) or not rule_id:
        raise ValueError("rule YAML missing required string field 'rule_id'")

    correction_text = payload.get("correction_text")
    if not isinstance(correction_text, str) or not correction_text:
        raise ValueError("rule YAML missing required string 'correction_text'")

    trigger = payload.get("trigger") or {}
    if not isinstance(trigger, dict):
        raise ValueError("'trigger' must be a mapping")
    trig_type = trigger.get("type", "log_regex")
    if trig_type == "log_regex":
        pattern = trigger.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError("log_regex trigger missing 'pattern'")
        predicate = _make_log_regex_predicate(
            pattern, exclude_pattern=trigger.get("exclude_pattern")
        )
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
            f"token_silence, completion_claim_without_commit, "
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
    ) -> None:
        self.agent_id = agent_id
        self.runtime_dir = Path(runtime_dir)
        self.rules_dir = Path(rules_dir) if rules_dir else None
        self.worktree = Path(worktree) if worktree else None
        self.agent_dir = self.runtime_dir / "agents" / agent_id
        self.agent_dir.mkdir(parents=True, exist_ok=True)
        self.registry = RuleRegistry()
        self.dispatcher = dispatcher or InjectionDispatcher()
        self.poll_interval = poll_interval
        self._log_offset = 0
        self._worktree_snapshot: dict[str, float] = {}
        self._worktree_baseline_taken = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # --- rule loading -----------------------------------------------------

    def load_rules(self) -> None:
        if self.rules_dir is not None:
            self.registry.load_dir(self.rules_dir)
        for err in self.registry.load_errors:
            append_load_error(self.agent_dir, err)

    # --- input collection -------------------------------------------------

    def collect_input(self) -> ObservedInput:
        return ObservedInput(
            agent_id=self.agent_id,
            log_lines=tuple(self._tail_output_log()),
            events=(),
            worktree_changes=tuple(self._scan_worktree()),
        )

    def _tail_output_log(self) -> list[str]:
        log_path = self.agent_dir / "output.log"
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

    def _scan_worktree(self) -> list[str]:
        if self.worktree is None or not self.worktree.exists():
            return []
        current: dict[str, float] = {}
        for p in self.worktree.rglob("*"):
            if p.is_file():
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
        corrections = self.registry.evaluate(ctx, agent_id=self.agent_id)
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
        return 0
    obs.start()
    try:
        while True:
            time.sleep(0.5)
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


def cmd_aggregate_approve(*, runtime_dir: Optional[Path] = None) -> int:
    """Stub. Full body in #L7 (aggregate-approve action)."""
    print(
        "observer: aggregate-approve stub (full body lands in #L7)",
        file=sys.stderr,
    )
    return 0


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

    agg_p = sub.add_parser("aggregate-approve", help="Stub — body in #L7")
    agg_p.add_argument("--runtime-dir", default=None)

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
        return cmd_aggregate_approve(runtime_dir=runtime)
    parser.error(f"unknown subcommand {args.subcommand!r}")
    return 2


def run(argv: list[str]) -> int:
    return main(argv)
