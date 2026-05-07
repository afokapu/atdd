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
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import yaml

import atdd
from atdd.coach.utils.config import load_atdd_config
from atdd.coach.utils.multiplexer import (
    MultiplexerBackend,
    MultiplexerError,
    get_multiplexer,
)
from atdd.coach.utils.session_naming import (
    branch_to_slug,
    compute_canonical_name,
    compute_repo_short_name,
    is_canonical_name,
    target_grid_label,
)


# =============================================================================
# Token-count alert (issue #378)
# =============================================================================
# Default threshold leaves ~200k headroom under the typical 600k effective cap,
# giving the worker enough budget to react to the alert (run /compact, optionally
# /clear and `atdd session-template <N> --from-checkpoint`).
DEFAULT_TOKEN_ALERT_THRESHOLD = 400_000


def load_token_alert_threshold(*, repo_root: Optional[Path] = None) -> int:
    """Resolve the token-alert threshold from .atdd/config.yaml or fall back to default."""
    base = Path(repo_root) if repo_root is not None else Path.cwd()
    try:
        config = load_atdd_config(base)
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow)
        # Malformed or unreadable config → fall back to the documented default.
        return DEFAULT_TOKEN_ALERT_THRESHOLD
    babysit_cfg = (config or {}).get("babysit") or {}
    value = babysit_cfg.get("token_alert_threshold")
    if isinstance(value, int) and value > 0:
        return value
    return DEFAULT_TOKEN_ALERT_THRESHOLD


def read_token_count(
    backend: MultiplexerBackend, workspace_ref: str
) -> Optional[int]:
    """Best-effort per-workspace token count via `claude --print-context-status`.

    Returns None when the binary is missing, the call errors, or the output is
    not parseable JSON. Callers must treat None as "unknown" — the dashboard
    renders this as "—" and no alert fires.

    Decision 6 (issue #378): the source mechanism is `claude --print-context-status`.
    A future revision can swap in a per-surface multiplexer command without
    changing the alert logic.
    """
    del workspace_ref  # reserved for future per-surface routing
    try:
        result = subprocess.run(
            ["claude", "--print-context-status"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):  # atdd:suppress(coder.logging.coach-silent-swallow)
        # Best-effort: claude binary missing or call errored → caller renders "—".
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):  # atdd:suppress(coder.logging.coach-silent-swallow)
        # Best-effort: stdout shape unrecognized → caller renders "—".
        return None
    for key in ("context_used_tokens", "tokens_used", "tokens"):
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, int):
            return value
    return None


def check_token_threshold(
    *, token_count: Optional[int], threshold: int
) -> Optional["BabysitDecision"]:
    """Return an escalation decision when the count crosses the threshold."""
    if token_count is None:
        return None
    if token_count < threshold:
        return None
    matched = f"token={token_count} threshold={threshold}"
    return BabysitDecision(
        action="escalate",
        matched=matched,
        reason=(
            f"token count {token_count} crossed threshold {threshold} — "
            "recommend /compact and `atdd session-template <N> --from-checkpoint`"
        ),
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
    """Result of analyzing a screen capture.

    Attributes:
        action: One of "auto_approve", "escalate", "violation", "idle".
        matched: Human-readable label of what fired the decision (rule
            description, literal token, or violation kind).
        reason: Free-text explanation of *why* the decision was made.
        rule_id: Stable rule ID when a structured classifier rule fired
            (e.g. COACH-BABYSIT-010); empty for legacy literal-match paths.
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


def _classify_bash_command(cmd: str) -> BabysitDecision:
    """Apply deny-then-allow regex matching to a single Bash command line."""
    for p in _DENY_PATTERNS:
        if p.regex.match(cmd):
            return BabysitDecision(
                action="escalate",
                matched=p.description,
                reason=p.rule_id,
                rule_id=p.rule_id,
            )
    for p in _ALLOW_PATTERNS:
        if p.regex.match(cmd):
            return BabysitDecision(
                action="auto_approve",
                matched=p.description,
                reason=p.rule_id,
                rule_id=p.rule_id,
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
# Session-naming + layout drift correction (issue #470)
# =============================================================================
# Both passes are idempotent: a rename/layout call only fires when drift is
# detected. Already-canonical names + already-conforming layouts are cheap
# no-ops. The applied-name cache lives for the lifetime of one babysit run
# and is keyed by surface ref; first-tick observation populates it from
# `.atdd/orchestrate-state.json`.


def _expected_canonical_name(
    issue_number: int,
    canonical_hint: str,
    config: Optional[Dict] = None,
) -> str:
    """Resolve the expected canonical name for an issue.

    Prefers the hint persisted by ``atdd orchestrate`` (when present in
    ``orchestrate-state.json::canonical_name``); otherwise computes from
    issue number + branch slug (best-effort, since the worktree ref does
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
    Issue #470 — coach.orchestration.canonical-session-name.
    """
    if not expected_name:
        return False
    if applied_cache.get(ref) == expected_name:
        return False
    try:
        backend.rename(ref, expected_name)
        backend.send(ref, f"/rename {expected_name}\n")
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
            "rule_id": "coach.orchestration.canonical-session-name",
        },
        path=log_path,
    )
    print(
        f"::notice::babysit auto-renamed {ref} → {expected_name} "
        f"(coach.orchestration.canonical-session-name)"
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
    helper logs the expected layout per Decision row 13 (drift-detection
    only — no per-tick shuffles). Returns True when the announcement was
    new this run; False when the layout band is unchanged.
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
            "rule_id": "coach.orchestration.layout-conformance",
        },
        path=log_path,
    )
    print(
        f"::notice::babysit layout target ({surface_count} surface[s]): {target} "
        f"(coach.orchestration.layout-conformance)"
    )
    return True


def _load_canonical_hints(
    orchestrate_state_path: Path,
) -> Dict[str, Tuple[int, str]]:
    """Read ``ref → (issue_number, canonical_name)`` from orchestrate state."""
    if not orchestrate_state_path.is_file():
        return {}
    try:
        data = json.loads(orchestrate_state_path.read_text())
    except (OSError, json.JSONDecodeError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        return {}
    out: Dict[str, Tuple[int, str]] = {}
    for key, entry in (data or {}).items():
        if not isinstance(entry, dict):
            continue
        ref = entry.get("ref") or entry.get("workspace_ref") or ""
        if not ref:
            continue
        try:
            issue_num = int(key)
        except (TypeError, ValueError):
            continue
        out[ref] = (issue_num, entry.get("canonical_name") or "")
    return out


# =============================================================================
# Telemetry
# =============================================================================

DEFAULT_LOG_PATH = Path(".atdd/orchestration-log.jsonl")
DEFAULT_ORCHESTRATE_STATE_PATH = Path(".atdd/orchestrate-state.json")


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
    token_alert_threshold: Optional[int] = None,
) -> BabysitDecision:
    try:
        screen = backend.read_screen(state.ref, lines=80)
    except MultiplexerError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
        log_event(
            {"event": "screen_read_error", "workspace": state.ref, "error": str(exc)},
            path=log_path,
        )
        return BabysitDecision(action="idle", reason=f"read error: {exc}")

    if token_alert_threshold is not None:
        token_count = read_token_count(backend, state.ref)
        token_decision = check_token_threshold(
            token_count=token_count, threshold=token_alert_threshold
        )
        if token_decision is not None:
            log_event(
                {
                    "event": "token_threshold",
                    "workspace": state.ref,
                    "token_count": token_count,
                    "threshold": token_alert_threshold,
                },
                path=log_path,
            )
            return token_decision

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
        except MultiplexerError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            log_event(
                {"event": "auto_approve_failed", "workspace": state.ref, "error": str(exc)},
                path=log_path,
            )
            return BabysitDecision(action="escalate", reason=f"send error: {exc}")
        approve_event: dict = {
            "event": "auto_approve",
            "workspace": state.ref,
            "matched": decision.matched,
        }
        if decision.rule_id:
            approve_event["pattern"] = decision.rule_id
        log_event(approve_event, path=log_path)
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


# =============================================================================
# Dashboard mode (issue #377)
# =============================================================================
# A second rendering layer over the existing event loop. Instead of streaming
# per-event lines to stdout, the dashboard repaints an aggregate table every
# `--interval`. State primitives (WorkspaceState, classifier, stale thresholds)
# are unchanged — only the surfacing of that state is new.

DEFAULT_PHASE_CACHE_SECONDS = 60
_PHASE_LABEL_PREFIX = "atdd:"


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


@dataclass
class AggregateApprovalResult:
    """Summary returned by `aggregate_approve` for `--approve-all-safe`."""

    approved: int = 0
    escalated: int = 0
    approvals_by_ref: Dict[str, str] = field(default_factory=dict)
    escalations_by_ref: Dict[str, str] = field(default_factory=dict)


def _load_orchestrate_state(path: Path) -> Dict[str, int]:
    """Invert the `{"<issue>": {"ref": "surface:NN", ...}}` map written by
    `atdd orchestrate` into `{ref: issue_num}`.

    Returns an empty dict if the file is missing or unreadable — the dashboard
    will then render `?`/`—` placeholders rather than crashing the loop.
    """
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):  # atdd:suppress(coder.logging.coach-silent-swallow)
        # Best-effort read for dashboard rendering. Falling back to {} causes
        # the dashboard to render `?`/`—` placeholders rather than crashing
        # the babysit loop, which is the documented behavior.
        return {}
    inverted: Dict[str, int] = {}
    for key, entry in (data or {}).items():
        if not isinstance(entry, dict):
            continue
        ref = entry.get("ref") or entry.get("workspace_ref") or ""
        if not ref:
            continue
        try:
            issue_num = int(key)
        except (TypeError, ValueError):
            continue
        inverted[ref] = issue_num
    return inverted


def _phase_from_labels(labels: List[dict]) -> str:
    """Return the first `atdd:<PHASE>` label value, or `?` when none present."""
    for label in labels or []:
        name = label.get("name") if isinstance(label, dict) else None
        if isinstance(name, str) and name.startswith(_PHASE_LABEL_PREFIX):
            return name[len(_PHASE_LABEL_PREFIX) :].upper() or "?"
    return "?"


def _fetch_phase_cache(issue_numbers: List[int]) -> Dict[int, str]:
    """Best-effort batched phase-label fetch. Returns issue→phase mapping.

    Uses a single `gh issue list` call (per Decision #2 in issue #377). On any
    failure (gh missing, network error, parse error) returns an empty dict so
    the dashboard renders `?` rather than crashing.
    """
    if not issue_numbers:
        return {}
    try:
        result = subprocess.run(
            [
                "gh", "issue", "list",
                "--state", "all",
                "--search", "assignee:@me",
                "--json", "number,labels",
                "--limit", "200",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):  # atdd:suppress(coder.logging.coach-silent-swallow)
        # Best-effort GitHub fetch. gh missing / offline / rate-limited all
        # collapse to "no phase data this cycle" — the dashboard renders `?`
        # for that issue and tries again next refresh.
        return {}
    try:
        records = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:  # atdd:suppress(coder.logging.coach-silent-swallow)
        # gh returned non-JSON (e.g. an error message on stdout). Same
        # fallback as the subprocess error path: render `?` and retry.
        return {}
    cache: Dict[int, str] = {}
    wanted = set(issue_numbers)
    for rec in records:
        num = rec.get("number")
        if num in wanted:
            cache[int(num)] = _phase_from_labels(rec.get("labels", []))
    return cache


def _extract_surface_state(
    *,
    ref: str,
    state: WorkspaceState,
    ref_to_issue: Dict[str, int],
    phase_cache: Dict[int, str],
    last_decision: Optional[BabysitDecision],
    now: float,
    stale_warn_minutes: int,
) -> SurfaceRow:
    """Build a `SurfaceRow` from a per-ref `WorkspaceState` + the latest
    classifier decision. Pure (no I/O)."""
    issue = ref_to_issue.get(ref)
    phase = phase_cache.get(issue, "?") if issue is not None else "?"
    elapsed = max(0.0, now - state.last_change_ts)
    stalled = elapsed >= stale_warn_minutes * 60

    pending_prompt = ""
    if last_decision is not None and last_decision.action == "escalate":
        kind = last_decision.matched or "Bash"
        pending_prompt = f"1 ({kind})"

    if last_decision is not None and last_decision.action == "violation":
        status = "violation"
    elif last_decision is not None and last_decision.action == "escalate":
        status = "escalated"
    elif stalled:
        status = "STALLED"
    else:
        status = "ACTIVE"

    return SurfaceRow(
        ref=ref,
        issue=issue,
        phase=phase,
        last_tool_seconds=elapsed,
        pending_prompt=pending_prompt,
        stalled=stalled,
        status=status,
    )


def _format_hms(seconds: float) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}"


def _render_dashboard(
    *,
    rows: List[SurfaceRow],
    now_iso: str,
    scope_label: str,
) -> str:
    """Render the aggregate table as a single string. Pure."""
    header = (
        f"ATDD Dashboard — {scope_label} ({len(rows)} surface(s), "
        f"refreshed {now_iso})"
    )
    sep = "─" * 78
    columns = (
        f"{'Surface':<14}{'Issue':<10}{'Phase':<10}"
        f"{'LastTool':<11}{'PendingPrompts':<18}{'Status'}"
    )
    body_lines: List[str] = []
    for row in rows:
        issue_str = f"#{row.issue}" if row.issue is not None else "—"
        last_tool = _format_hms(row.last_tool_seconds)
        pending = row.pending_prompt or "0"
        body_lines.append(
            f"{row.ref:<14}{issue_str:<10}{row.phase:<10}"
            f"{last_tool:<11}{pending:<18}{row.status}"
        )
    return "\n".join([header, sep, columns, sep, *body_lines, sep])


def aggregate_approve(
    *,
    backend: MultiplexerBackend,
    refs: List[str],
    log_path: Path = DEFAULT_LOG_PATH,
) -> AggregateApprovalResult:
    """Sweep every ref in `refs`, run the existing classifier, and auto-approve
    matches. Escalations and violations are recorded but not approved.

    Each approval is appended to `log_path` as `event=agg_approve` with the
    matching rule_id and a `reason` prefixed `agg-approve: ` so the action is
    auditable in `orchestration-log.jsonl`.
    """
    result = AggregateApprovalResult()
    for ref in refs:
        try:
            screen = backend.read_screen(ref, lines=80)
        except MultiplexerError as exc:
            log_event(
                {"event": "screen_read_error", "workspace": ref, "error": str(exc)},
                path=log_path,
            )
            continue

        violation = detect_violation(screen)
        if violation is not None:
            result.escalated += 1
            result.escalations_by_ref[ref] = violation.reason or "violation"
            continue

        decision = classify_prompt(screen)
        if decision.action == "auto_approve":
            try:
                backend.send(ref, "1")
                backend.send_key(ref, "Enter")
            except MultiplexerError as exc:
                log_event(
                    {
                        "event": "agg_approve_failed",
                        "workspace": ref,
                        "error": str(exc),
                    },
                    path=log_path,
                )
                result.escalated += 1
                result.escalations_by_ref[ref] = f"send error: {exc}"
                continue
            description = decision.matched or "auto-approve"
            log_event(
                {
                    "event": "agg_approve",
                    "workspace": ref,
                    "matched": description,
                    "pattern": decision.rule_id or "",
                    "reason": f"agg-approve: {description}",
                },
                path=log_path,
            )
            result.approved += 1
            result.approvals_by_ref[ref] = decision.rule_id or "auto"
        elif decision.action == "escalate":
            result.escalated += 1
            result.escalations_by_ref[ref] = decision.reason or "escalate"
        # idle → no-op
    return result


# =============================================================================
# Main loop
# =============================================================================


def _scope_label(refs: List[str]) -> str:
    if not refs:
        return "(none)"
    if len(refs) <= 3:
        return ", ".join(refs)
    return f"{len(refs)} surfaces"


def run(
    interval: int = 60,
    workspaces: Optional[list[str]] = None,
    stale_warn: int = 15,
    stale_escalate: int = 30,
    once: bool = False,
    multiplexer: Optional[str] = None,
    log_path: Path = DEFAULT_LOG_PATH,
    dashboard: bool = False,
    approve_all_safe: bool = False,
    orchestrate_state_path: Path = DEFAULT_ORCHESTRATE_STATE_PATH,
    phase_cache_seconds: int = DEFAULT_PHASE_CACHE_SECONDS,
    phase_fetcher: Optional[Callable[[List[int]], Dict[int, str]]] = None,
    token_alert_threshold: Optional[int] = None,
) -> int:
    try:
        backend = get_multiplexer(preferred=multiplexer)
    except MultiplexerError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
        print(f"❌ {exc}")
        return 1

    if workspaces is None:
        try:
            workspaces = backend.list_workspaces()
        except MultiplexerError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"❌ {exc}")
            return 1

    if not workspaces:
        print("⚠️  no workspaces to babysit")
        return 0

    if approve_all_safe:
        result = aggregate_approve(backend=backend, refs=workspaces, log_path=log_path)
        print(f"{result.approved} prompts auto-approved")
        print(f"{result.escalated} prompts escalated (kept for manual review)")
        return 0

    if token_alert_threshold is None:
        token_alert_threshold = load_token_alert_threshold()

    states = {ref: WorkspaceState(ref=ref) for ref in workspaces}
    last_decisions: Dict[str, Optional[BabysitDecision]] = {ref: None for ref in workspaces}
    print(f"👀 babysitting {len(states)} workspace(s): {', '.join(states)}")

    fetcher = phase_fetcher or _fetch_phase_cache
    phase_cache: Dict[int, str] = {}
    phase_cache_ts: float = 0.0

    # Issue #470: drift-correction caches. Keys are surface refs; values are
    # the last-applied canonical name. Idempotency contract: a rename only
    # fires when the cache entry differs from the expected name.
    name_applied_cache: Dict[str, str] = {}
    layout_cache: Dict[str, str] = {}
    canonical_hints = _load_canonical_hints(orchestrate_state_path)

    while True:
        # Issue #470 — paired naming + layout pass. Idempotent: only fires
        # on drift. Scoped to the workspaces babysit is already monitoring,
        # so other cmux surfaces (operator shell, unrelated worktrees) are
        # untouched.
        for ref in states:
            hint = canonical_hints.get(ref)
            if hint is None:
                continue
            issue_num, hint_name = hint
            expected = _expected_canonical_name(issue_num, hint_name)
            correct_naming_drift(
                backend=backend,
                ref=ref,
                expected_name=expected,
                applied_cache=name_applied_cache,
                log_path=log_path,
            )
        correct_layout_drift(
            surface_count=len(states),
            layout_cache=layout_cache,
            log_path=log_path,
        )

        for ref, st in states.items():
            decision = process_workspace(
                backend, st, stale_warn, stale_escalate,
                log_path=log_path,
                token_alert_threshold=token_alert_threshold,
            )
            last_decisions[ref] = decision
            if not dashboard and decision.action != "idle":
                print(f"  [{ref}] {decision.action}: {decision.matched or decision.reason}")

        if dashboard:
            now = time.time()
            ref_to_issue = _load_orchestrate_state(orchestrate_state_path)
            if (now - phase_cache_ts) >= phase_cache_seconds:
                phase_cache = fetcher(sorted(set(ref_to_issue.values())))
                phase_cache_ts = now

            rows = [
                _extract_surface_state(
                    ref=ref,
                    state=states[ref],
                    ref_to_issue=ref_to_issue,
                    phase_cache=phase_cache,
                    last_decision=last_decisions[ref],
                    now=now,
                    stale_warn_minutes=stale_warn,
                )
                for ref in states
            ]
            now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
            output = _render_dashboard(
                rows=rows, now_iso=now_iso, scope_label=_scope_label(list(states))
            )
            # Clear screen + home cursor before repaint, per Decision #5/#6.
            print("\033[2J\033[H", end="")
            print(output, flush=True)

        if once:
            return 0
        try:
            time.sleep(interval)
        except KeyboardInterrupt:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print("\n👋 babysitter stopped")
            return 0
