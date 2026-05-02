"""
`atdd babysit` — parallel-session monitor.

Polls multiplexer workspaces, auto-approves known-safe tool prompts,
escalates unknown prompts, and detects policy violations (`.atdd/` hand-edits,
SMOKE skips, hallucinated completion).

Events are appended to `.atdd/orchestration-log.jsonl` as JSON Lines.

SPEC IDs: SPEC-COACH-ORCH-0004, SPEC-COACH-ORCH-0005
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

import atdd
from atdd.coach.utils.multiplexer import (
    MultiplexerBackend,
    MultiplexerError,
    get_multiplexer,
)


# =============================================================================
# Prompt approval — literal string match for non-Bash tools
# =============================================================================

KNOWN_SAFE_PROMPTS: tuple[str, ...] = (
    "Read",
    "Grep",
    "Glob",
    "Edit",
    "git status",
    "git diff",
    "git log",
)

# Bash is intentionally absent — the pattern-based classifier below decides
# per-command. See orchestration.convention.yaml::babysit.bash_*_patterns.
ALWAYS_ESCALATE_PROMPTS: tuple[str, ...] = (
    "Write",
    "rm ",
    "git push --force",
)


# =============================================================================
# Bash pattern classifier (issue #366)
# =============================================================================
# Allow / deny regex patterns are sourced from
# orchestration.convention.yaml::babysit.bash_*_patterns.rules. Each rule has
# a stable rule_id under DOMAIN=COACH (SPEC-COACH-RULEID-0001).


@dataclass(frozen=True)
class BashPattern:
    """One allow- or deny-list entry as compiled at module load time."""

    rule_id: str
    severity: int
    description: str
    regex: re.Pattern[str]


_ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
_ORCHESTRATION_CONVENTION = (
    _ATDD_PKG_DIR / "coach" / "conventions" / "orchestration.convention.yaml"
)
_PROMPT_MARKERS: tuple[str, ...] = (
    "Do you want to proceed?",
    "Approve this tool use?",
    "❯ 1. Yes",
    "1) Yes, approve",
)


def _load_bash_patterns() -> Tuple[List[BashPattern], List[BashPattern]]:
    """Load (allow_patterns, deny_patterns) from the orchestration convention.

    Raises FileNotFoundError if the convention is missing, and re.error if any
    regex fails to compile. Both are loud failures by design — the validator
    in src/atdd/coach/validators/test_babysit_allowlist_consistency.py catches
    them at CI time.
    """
    if not _ORCHESTRATION_CONVENTION.is_file():
        raise FileNotFoundError(
            f"orchestration convention missing at {_ORCHESTRATION_CONVENTION}"
        )
    with _ORCHESTRATION_CONVENTION.open() as fh:
        data = yaml.safe_load(fh) or {}
    babysit_block = data.get("babysit") or {}

    def _compile(key: str) -> List[BashPattern]:
        block = babysit_block.get(key) or {}
        rules = block.get("rules") or []
        compiled: List[BashPattern] = []
        for rule in rules:
            compiled.append(
                BashPattern(
                    rule_id=rule["id"],
                    severity=int(rule["severity"]),
                    description=rule["description"],
                    regex=re.compile(rule["regex"]),
                )
            )
        return compiled

    return _compile("bash_auto_approve_patterns"), _compile("bash_deny_patterns")


_ALLOW_PATTERNS, _DENY_PATTERNS = _load_bash_patterns()


@dataclass
class WorkspaceState:
    ref: str
    last_screen_hash: str = ""
    last_change_ts: float = field(default_factory=time.time)


@dataclass
class BabysitDecision:
    """Result of analyzing a screen capture."""
    action: str  # "auto_approve" | "escalate" | "violation" | "idle"
    matched: str = ""
    reason: str = ""


def _contains_prompt_marker(screen: str) -> bool:
    """Detect Claude Code tool-use prompt markers (literal strings, no regex)."""
    return any(m in screen for m in _PROMPT_MARKERS)


def _prompt_marker_position(screen: str) -> int:
    """Return the latest prompt-marker offset, or -1 if none present."""
    pos = -1
    for marker in _PROMPT_MARKERS:
        idx = screen.rfind(marker)
        if idx > pos:
            pos = idx
    return pos


def extract_bash_command(screen: str) -> Optional[str]:
    """Extract the Bash command from a prompt screen capture.

    Looks for the most recent ``Bash(...)`` invocation occurring before the
    Y/N prompt marker and returns the contents of the balanced parens with
    surrounding whitespace stripped. Returns ``None`` when no Bash prompt is
    present or when parens are unbalanced.
    """
    marker_idx = _prompt_marker_position(screen)
    if marker_idx == -1:
        return None
    head = screen[:marker_idx]
    open_idx = head.rfind("Bash(")
    if open_idx == -1:
        return None
    start = open_idx + len("Bash(")
    depth = 1
    i = start
    n = len(screen)
    while i < n and depth > 0:
        ch = screen[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        i += 1
    if depth != 0:
        return None
    return screen[start : i - 1].strip()


def _classify_bash_command(cmd: str) -> BabysitDecision:
    """Apply deny-then-allow regex matching to a single Bash command line."""
    for p in _DENY_PATTERNS:
        if p.regex.match(cmd):
            return BabysitDecision(
                action="escalate",
                matched=p.description,
                reason=p.rule_id,
            )
    for p in _ALLOW_PATTERNS:
        if p.regex.match(cmd):
            return BabysitDecision(
                action="auto_approve",
                matched=p.description,
                reason=p.rule_id,
            )
    return BabysitDecision(
        action="escalate",
        reason="unknown bash command — no allow/deny match",
    )


def classify_prompt(screen: str) -> BabysitDecision:
    """Classify the latest prompt visible in a screen capture.

    Rules:
    - If no prompt marker → idle.
    - If any ALWAYS_ESCALATE token appears near the prompt → escalate.
    - If the prompt is a Bash invocation → run the pattern classifier.
    - Otherwise, if a KNOWN_SAFE token appears → auto_approve.
    - Otherwise → escalate (unknown).
    """
    if not _contains_prompt_marker(screen):
        return BabysitDecision(action="idle")

    # Dangerous non-Bash writes take precedence.
    for token in ALWAYS_ESCALATE_PROMPTS:
        if token in screen:
            return BabysitDecision(
                action="escalate",
                matched=token,
                reason="always-escalate pattern detected",
            )

    if "Bash(" in screen:
        cmd = extract_bash_command(screen)
        if cmd is None:
            return BabysitDecision(
                action="escalate",
                reason="bash command extraction failed",
            )
        return _classify_bash_command(cmd)

    for token in KNOWN_SAFE_PROMPTS:
        if token in screen:
            return BabysitDecision(
                action="auto_approve",
                matched=token,
                reason="known-safe tool prompt",
            )

    return BabysitDecision(
        action="escalate",
        reason="unknown prompt — no known-safe match",
    )


def detect_violation(screen: str) -> Optional[BabysitDecision]:
    """Scan a screen for policy violations. Returns a decision or None."""
    if "Edit" in screen and ".atdd/" in screen:
        return BabysitDecision(
            action="violation",
            matched=".atdd/ hand-edit",
            reason=".atdd/ files are managed by the CLI — never hand-edited",
        )
    if "--status REFACTOR" in screen and "SMOKE" not in screen:
        return BabysitDecision(
            action="violation",
            matched="SMOKE skip",
            reason="transition to REFACTOR without passing through SMOKE",
        )
    return None


# =============================================================================
# Telemetry
# =============================================================================

DEFAULT_LOG_PATH = Path(".atdd/orchestration-log.jsonl")


def log_event(event: dict, path: Path = DEFAULT_LOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event.setdefault("ts", datetime.now(timezone.utc).isoformat())
    with path.open("a") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


# =============================================================================
# Main loop
# =============================================================================


def _screen_hash(screen: str) -> str:
    return hashlib.sha1(screen.encode("utf-8", errors="replace")).hexdigest()


def process_workspace(
    backend: MultiplexerBackend,
    state: WorkspaceState,
    stale_warn_minutes: int,
    stale_escalate_minutes: int,
    log_path: Path = DEFAULT_LOG_PATH,
) -> BabysitDecision:
    try:
        screen = backend.read_screen(state.ref, lines=80)
    except MultiplexerError as exc:
        log_event(
            {"event": "screen_read_error", "workspace": state.ref, "error": str(exc)},
            path=log_path,
        )
        return BabysitDecision(action="idle", reason=f"read error: {exc}")

    digest = _screen_hash(screen)
    now = time.time()
    if digest != state.last_screen_hash:
        state.last_screen_hash = digest
        state.last_change_ts = now

    log_event(
        {
            "event": "screen_read",
            "workspace": state.ref,
            "screen_hash": digest,
            "bytes": len(screen),
        },
        path=log_path,
    )

    idle_minutes = (now - state.last_change_ts) / 60.0
    if idle_minutes >= stale_escalate_minutes:
        decision = BabysitDecision(
            action="escalate",
            matched="stale",
            reason=f"no screen change for {idle_minutes:.1f}m (>= {stale_escalate_minutes})",
        )
        log_event(
            {"event": "session_stale_escalate", "workspace": state.ref, "idle_m": idle_minutes},
            path=log_path,
        )
        return decision
    if idle_minutes >= stale_warn_minutes:
        log_event(
            {"event": "session_stale_warn", "workspace": state.ref, "idle_m": idle_minutes},
            path=log_path,
        )

    violation = detect_violation(screen)
    if violation is not None:
        log_event(
            {
                "event": "violation",
                "workspace": state.ref,
                "matched": violation.matched,
                "reason": violation.reason,
            },
            path=log_path,
        )
        return violation

    decision = classify_prompt(screen)
    if decision.action == "auto_approve":
        try:
            backend.send(state.ref, "1")
            backend.send_key(state.ref, "Enter")
        except MultiplexerError as exc:
            log_event(
                {"event": "auto_approve_failed", "workspace": state.ref, "error": str(exc)},
                path=log_path,
            )
            return BabysitDecision(action="escalate", reason=f"send error: {exc}")
        log_event(
            {
                "event": "auto_approve",
                "workspace": state.ref,
                "matched": decision.matched,
                "pattern": decision.reason,
            },
            path=log_path,
        )
    elif decision.action == "escalate":
        log_event(
            {
                "event": "escalate",
                "workspace": state.ref,
                "matched": decision.matched,
                "reason": decision.reason,
            },
            path=log_path,
        )
    return decision


def run(
    interval: int = 60,
    workspaces: Optional[list[str]] = None,
    stale_warn: int = 15,
    stale_escalate: int = 30,
    once: bool = False,
    multiplexer: Optional[str] = None,
    log_path: Path = DEFAULT_LOG_PATH,
) -> int:
    try:
        backend = get_multiplexer(preferred=multiplexer)
    except MultiplexerError as exc:
        print(f"❌ {exc}")
        return 1

    if workspaces is None:
        try:
            workspaces = backend.list_workspaces()
        except MultiplexerError as exc:
            print(f"❌ {exc}")
            return 1

    if not workspaces:
        print("⚠️  no workspaces to babysit")
        return 0

    states = {ref: WorkspaceState(ref=ref) for ref in workspaces}
    print(f"👀 babysitting {len(states)} workspace(s): {', '.join(states)}")

    while True:
        for ref, st in states.items():
            decision = process_workspace(
                backend, st, stale_warn, stale_escalate, log_path=log_path
            )
            if decision.action != "idle":
                print(f"  [{ref}] {decision.action}: {decision.matched or decision.reason}")
        if once:
            return 0
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n👋 babysitter stopped")
            return 0
