# URN: component:observe-and-correct:observer-runtime-and-rules:detectors:backend:application
# Runtime: python
# Purpose: Pure prompt-classification + drift-correction detectors backing observer rules 13-16.

"""Detection + correction primitives for observer rules 13-16 (spec §8.3).

These functions are first-class observer code: a screen-capture classifier
(``classify_prompt``), a policy-violation scanner (``detect_violation``), and
the canonical-name / layout drift correctors (``correct_naming_drift`` /
``correct_layout_drift``). The Bash allow/deny pattern set is sourced from
``observer.convention.yaml::bash_classifier`` (``auto_approve_patterns`` and
``deny_patterns``).

Each rule module under ``observer_rules/`` imports the primitive it needs and
wraps it in an :class:`~atdd.coach.commands.observer.ObserverRule` factory.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

import atdd
from atdd.coach.utils.multiplexer import MultiplexerBackend, MultiplexerError
from atdd.coach.utils.session_naming import (
    compute_canonical_name,
    compute_repo_short_name,
    is_canonical_name,
    target_grid_label,
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
# per-command. See observer.convention.yaml::bash_classifier.
ALWAYS_ESCALATE_PROMPTS: tuple[str, ...] = (
    "Write",
    "rm ",
    "git push --force",
)


# =============================================================================
# Bash pattern classifier (issue #366)
# =============================================================================
# Allow / deny regex patterns are sourced from
# observer.convention.yaml::bash_classifier.{auto_approve_patterns,deny_patterns}.
# Each rule has a stable rule_id under DOMAIN=COACH (SPEC-COACH-RULEID-0001).


@dataclass(frozen=True)
class BashPattern:
    """One allow- or deny-list entry as compiled at module load time."""

    rule_id: str
    severity: int
    description: str
    regex: re.Pattern[str]


_ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
_OBSERVER_CONVENTION = (
    _ATDD_PKG_DIR / "coach" / "conventions" / "observer.convention.yaml"
)
_PROMPT_MARKERS: tuple[str, ...] = (
    "Do you want to proceed?",
    "Approve this tool use?",
    "❯ 1. Yes",
    "1) Yes, approve",
)


def _load_bash_patterns() -> Tuple[List[BashPattern], List[BashPattern]]:
    """Load (allow_patterns, deny_patterns) from the observer convention.

    Raises FileNotFoundError if the convention is missing, and re.error if any
    regex fails to compile. Both are loud failures by design.
    """
    if not _OBSERVER_CONVENTION.is_file():
        raise FileNotFoundError(
            f"observer convention missing at {_OBSERVER_CONVENTION}"
        )
    with _OBSERVER_CONVENTION.open() as fh:
        data = yaml.safe_load(fh) or {}
    classifier_block = data.get("bash_classifier") or {}

    def _compile(key: str) -> List[BashPattern]:
        block = classifier_block.get(key) or {}
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

    return _compile("auto_approve_patterns"), _compile("deny_patterns")


_ALLOW_PATTERNS, _DENY_PATTERNS = _load_bash_patterns()


@dataclass
class ObserverDecision:
    """Result of analyzing a screen capture.

    Attributes:
        action: One of "auto_approve", "escalate", "violation", "idle".
        matched: Human-readable label of what fired the decision (rule
            description, literal token, or violation kind).
        reason: Free-text explanation of *why* the decision was made.
        rule_id: Stable rule ID when a structured classifier rule fired
            (e.g. coach.observer.bash-read-only-git-diagnostics); empty for
            literal-match paths.
    """

    action: str  # "auto_approve" | "escalate" | "violation" | "idle"
    matched: str = ""
    reason: str = ""
    rule_id: str = ""


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


def _classify_bash_command(cmd: str) -> ObserverDecision:
    """Apply deny-then-allow regex matching to a single Bash command line."""
    for p in _DENY_PATTERNS:
        if p.regex.match(cmd):
            return ObserverDecision(
                action="escalate",
                matched=p.description,
                reason=p.rule_id,
                rule_id=p.rule_id,
            )
    for p in _ALLOW_PATTERNS:
        if p.regex.match(cmd):
            return ObserverDecision(
                action="auto_approve",
                matched=p.description,
                reason=p.rule_id,
                rule_id=p.rule_id,
            )
    return ObserverDecision(
        action="escalate",
        reason="unknown bash command — no allow/deny match",
    )


def classify_prompt(screen: str) -> ObserverDecision:
    """Classify the latest prompt visible in a screen capture.

    Rules:
    - If no prompt marker → idle.
    - If any ALWAYS_ESCALATE token appears near the prompt → escalate.
    - If the prompt is a Bash invocation → run the pattern classifier.
    - Otherwise, if a KNOWN_SAFE token appears → auto_approve.
    - Otherwise → escalate (unknown).
    """
    if not _contains_prompt_marker(screen):
        return ObserverDecision(action="idle")

    # Dangerous non-Bash writes take precedence.
    for token in ALWAYS_ESCALATE_PROMPTS:
        if token in screen:
            return ObserverDecision(
                action="escalate",
                matched=token,
                reason="always-escalate pattern detected",
            )

    if "Bash(" in screen:
        cmd = extract_bash_command(screen)
        if cmd is None:
            return ObserverDecision(
                action="escalate",
                reason="bash command extraction failed",
            )
        return _classify_bash_command(cmd)

    for token in KNOWN_SAFE_PROMPTS:
        if token in screen:
            return ObserverDecision(
                action="auto_approve",
                matched=token,
                reason="known-safe tool prompt",
            )

    return ObserverDecision(
        action="escalate",
        reason="unknown prompt — no known-safe match",
    )


def detect_violation(screen: str) -> Optional[ObserverDecision]:
    """Scan a screen for policy violations. Returns a decision or None."""
    if "Edit" in screen and ".atdd/" in screen:
        return ObserverDecision(
            action="violation",
            matched=".atdd/ hand-edit",
            reason=".atdd/ files are managed by the CLI — never hand-edited",
        )
    if "--status REFACTOR" in screen and "SMOKE" not in screen:
        return ObserverDecision(
            action="violation",
            matched="SMOKE skip",
            reason="transition to REFACTOR without passing through SMOKE",
        )
    return None


# =============================================================================
# Session-naming + layout drift correction (issue #470)
# =============================================================================
# Both passes are idempotent: a rename/layout call only fires when drift is
# detected. Already-canonical names + already-conforming layouts are cheap
# no-ops. The applied-name cache lives for the lifetime of one observer run
# and is keyed by surface ref.


def _expected_canonical_name(
    issue_number: int,
    canonical_hint: str,
    config: Optional[Dict] = None,
) -> str:
    """Resolve the expected canonical name for an issue.

    Prefers the persisted hint (when already canonical); otherwise computes
    from issue number + branch slug (best-effort, since the worktree ref does
    not always carry branch info).
    """
    if canonical_hint and is_canonical_name(canonical_hint):
        return canonical_hint
    repo_short = compute_repo_short_name(config or {})
    return compute_canonical_name(repo_short, issue_number, f"issue-{issue_number}")


def correct_naming_drift(
    backend: MultiplexerBackend,
    ref: str,
    expected_name: str,
    applied_cache: Dict[str, str],
    *,
    log_path: Path,
) -> bool:
    """Re-apply the canonical name to ``ref`` when drift is detected.

    Idempotent — once we've applied ``expected_name`` to ``ref`` in this
    run, subsequent ticks short-circuit. Returns True when a rename was
    actually issued (drift corrected); False when already canonical.
    Issue #470 — coach.session.canonical-session-name.
    """
    if not expected_name:
        return False
    if applied_cache.get(ref) == expected_name:
        return False
    try:
        # Multiplexer-level rename only. The Claude /rename slash-command
        # injection was removed by M001 (#829) — naming is set by the
        # cmux-native launch metadata; the observer only re-applies the
        # tab/window title here. See session.convention.yaml.
        backend.rename(ref, expected_name)
    except MultiplexerError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        # Best-effort: log + retry next tick.
        log_event(
            {
                "event": "session_rename_failed",
                "workspace": ref,
                "expected": expected_name,
                "error": str(exc),
            },
            path=log_path,
        )
        return False
    applied_cache[ref] = expected_name
    log_event(
        {
            "event": "session_renamed",
            "workspace": ref,
            "to": expected_name,
            "rule_id": "coach.session.canonical-session-name",
        },
        path=log_path,
    )
    print(
        f"::notice::observer auto-renamed {ref} → {expected_name} "
        f"(coach.session.canonical-session-name)"
    )
    return True


def correct_layout_drift(
    surface_count: int,
    layout_cache: Dict[str, str],
    *,
    log_path: Path,
) -> bool:
    """Announce the target grid label when surface_count crosses a threshold.

    Layout rebalancing across cmux panes is the multiplexer's job; this
    helper logs the expected layout (drift-detection only — no per-tick
    shuffles). Returns True when the announcement was new this run; False
    when the layout band is unchanged.
    """
    target = target_grid_label(surface_count)
    if layout_cache.get("last_target") == target:
        return False
    layout_cache["last_target"] = target
    log_event(
        {
            "event": "layout_target",
            "surface_count": surface_count,
            "target": target,
            "rule_id": "coach.session.layout-conformance",
        },
        path=log_path,
    )
    print(
        f"::notice::observer layout target ({surface_count} surface[s]): {target} "
        f"(coach.session.layout-conformance)"
    )
    return True


# =============================================================================
# Telemetry
# =============================================================================

DEFAULT_LOG_PATH = Path(".atdd/observer-log.jsonl")


def log_event(event: dict, path: Path = DEFAULT_LOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event.setdefault("ts", datetime.now(timezone.utc).isoformat())
    with path.open("a") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")
