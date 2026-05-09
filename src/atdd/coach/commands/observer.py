"""`atdd observer <subcommand>` — coach v9 L1 observer skeleton (issue #500).

Event-driven detect-and-correct sidecar per agent. Tails the agent's
``output.log``, watches the worktree, evaluates a YAML-discovered rule
registry, and dispatches corrections through one of three injection
paths (CLI return-path / multiplexer send-keys / kill-and-respawn).

This module is the *runtime* + *registry* + *injection* foundation.
The 17 default detection rules ship in #L2-#L5; this skeleton has zero
detection-rule body of its own — it only owns the surface those rules
plug into.

Subcommands per spec §5.4:
    run                — start the observer for an agent (tail + evaluate loop)
    attach             — print recent observations for an agent
    status             — dashboard (stub here; full body in #L6)
    aggregate-approve  — batch approval action (stub here; full body in #L7)

Out of scope:
- The 17 default detection rules (#L2-#L5).
- The `status` dashboard body (#L6).
- The `aggregate-approve` action body (#L7).
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
    """Snapshot of the agent's runtime state for one evaluation pass."""

    agent_id: str
    log_lines: tuple[str, ...] = ()
    events: tuple[dict, ...] = ()
    worktree_changes: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Observer rule
# ---------------------------------------------------------------------------


Predicate = Callable[[ObservedInput], bool]


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
        if self.predicate(ctx):
            return Correction(
                agent_id=agent_id,
                rule_id=self.rule_id,
                severity=self.severity,
                disposition=self.disposition,
                correction_text=self.correction_text,
                injection_method=self.injection_method,
                issued_at=_now_iso_z(),
            )
        return None


# ---------------------------------------------------------------------------
# Rule loader
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleLoadError:
    path: Path
    reason: str


def _make_log_regex_predicate(pattern: str) -> Predicate:
    import re

    rx = re.compile(pattern)

    def predicate(ctx: ObservedInput) -> bool:
        return any(rx.search(line) for line in ctx.log_lines)

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
        predicate = _make_log_regex_predicate(pattern)
    elif trig_type == "never":
        predicate = lambda _ctx: False  # noqa: E731 — terse intentional
    else:
        raise ValueError(
            f"unknown trigger.type {trig_type!r} (supported: log_regex, never)"
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


def cmd_status(*, runtime_dir: Optional[Path] = None) -> int:
    """Stub. Full body in #L6 (status dashboard)."""
    runtime = _runtime_root(runtime_dir)
    agents_dir = runtime / "agents"
    if not agents_dir.exists():
        print("observer: no agents under runtime")
        return 0
    print("observer: known agents:")
    for child in sorted(agents_dir.iterdir()):
        if child.is_dir():
            print(f"  - {child.name}")
    print("(status dashboard body lands in #L6)")
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
