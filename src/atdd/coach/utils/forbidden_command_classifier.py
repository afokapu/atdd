# URN: component:integration-hardening:coach-single-command-driver:forbidden_command_classifier:backend:domain
# Runtime: python
# Purpose: Classify Bash commands against the forbidden-command registry; block forbidden patterns.
"""Forbidden-command classifier for the claude-code pre-tool-use hook (issue #668, L1).

Reads ``src/atdd/coach/conventions/forbidden_commands.convention.yaml`` and
classifies each Bash command as ``block`` or ``allow``.

Decision 6 (issue #668): if the registry fails to load the classifier fails
OPEN — every command is allowed and a warning is printed to stderr.

Two enforcement modes:
  hard_block  — always blocked; every match exits 2.
  loop_block  — allowed on the first call within the TTL window; blocked on
                subsequent calls OR when the command string itself contains a
                loop construct (``while``, ``until``, or ``for ``).

Audit log:
  Every classify() call appends one JSON record to
  ``.atdd/runtime/tool_use_audit.jsonl`` under the repo root.

Loop state:
  ``.atdd/runtime/tool_use_counts.json`` under the repo root tracks per-rule
  call timestamps so the threshold/TTL window can be enforced across calls.

Hook entry point:
  Run as a script:  python3 forbidden_command_classifier.py <repo_root>
  Reads Claude Code JSON payload from stdin; prints "block\\n<rule>\\n<reason>\\n<alt>"
  or "allow" to stdout.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import yaml


_logger = logging.getLogger(__name__)

_CONVENTION_PATH = (
    Path(__file__).resolve().parent.parent / "conventions" / "forbidden_commands.convention.yaml"
)
_AUDIT_LOG_RELPATH = ".atdd/runtime/tool_use_audit.jsonl"
_LOOP_STATE_RELPATH = ".atdd/runtime/tool_use_counts.json"

# Command tokens that indicate the command itself is a loop construct.
_LOOP_TOKENS = ("while ", "until ", "for ")


@dataclass(frozen=True)
class Decision:
    """Result of classifying one command."""

    action: str  # "block" or "allow"
    rule_id: Optional[str] = None
    reason: Optional[str] = None
    alternative: Optional[str] = None


def _load_registry(convention_path: Path) -> List[dict]:
    """Load pattern list from the convention YAML; returns [] on any failure."""
    try:
        with convention_path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data.get("patterns", [])
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) Fail open per Decision 6 in issue #668
        _logger.warning("forbidden_command_classifier: failed to load registry %s: %s", convention_path, exc)  # atdd:suppress(coder.logging.structured) UNTIL=2026-10-31
        return []


def _matches(command: str, match_spec: dict) -> bool:
    """Return True when *command* satisfies the match specification."""
    if "contains" in match_spec:
        return match_spec["contains"] in command

    if "contains_all" in match_spec:
        return all(s in command for s in match_spec["contains_all"])

    if "contains_any" in match_spec:
        return any(s in command for s in match_spec["contains_any"])

    if "regex" in match_spec:
        return bool(re.search(match_spec["regex"], command))

    return False


def _is_loop_command(command: str) -> bool:
    """Return True when the command string itself is a loop construct."""
    return any(token in command for token in _LOOP_TOKENS)


def _check_and_record_loop_call(
    rule_id: str,
    threshold: int,
    ttl_seconds: int,
    state_file: Path,
) -> bool:
    """Return True when this call should be blocked due to frequency.

    Loads the state file, prunes expired entries, checks whether the
    accumulated call count already meets or exceeds *threshold*, then appends
    the current timestamp and saves.  Returns True (block) before appending
    when threshold is already met so the caller's call is not counted.
    """
    now = time.time()
    state: dict = {}

    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) Corrupt state is non-fatal; reset to empty
            _logger.warning("forbidden_command_classifier: corrupt loop state, resetting: %s", exc)  # atdd:suppress(coder.logging.structured) UNTIL=2026-10-31
            state = {}

    calls: list = state.get(rule_id, [])
    calls = [t for t in calls if now - t < ttl_seconds]

    if len(calls) >= threshold:
        return True  # Threshold met — block without recording this call

    calls.append(now)
    state[rule_id] = calls
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state), encoding="utf-8")
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) Loop state is best-effort; failure must not block tool use
        _logger.warning("forbidden_command_classifier: failed to write loop state: %s", exc)  # atdd:suppress(coder.logging.structured) UNTIL=2026-10-31

    return False  # Within threshold — allow


def _write_audit(
    command: str,
    tool: str,
    decision: Decision,
    audit_file: Path,
) -> None:
    """Append one JSON record to the audit log; best-effort (never raises)."""
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": tool,
        "command": command[:500],
        "decision": decision.action,
        "rule_id": decision.rule_id,
        "reason": decision.reason,
        "alternative": decision.alternative,
    }
    try:
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        with audit_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) Audit writes are best-effort; loss must not block tool use
        _logger.warning("forbidden_command_classifier: failed to write audit log: %s", exc)  # atdd:suppress(coder.logging.structured) UNTIL=2026-10-31


def classify(
    command: str,
    tool: str = "Bash",
    repo_root: Optional[Path] = None,
    convention_path: Optional[Path] = None,
) -> Decision:
    """Classify *command* against the forbidden-command registry.

    Args:
        command:         The raw Bash command string.
        tool:            Tool name for the audit record (default "Bash").
        repo_root:       Repo root used for audit log and loop state paths.
                         Defaults to Path.cwd().
        convention_path: Override the convention YAML path (used in tests).

    Returns:
        Decision with action ``"block"`` or ``"allow"``.
    """
    if repo_root is None:
        repo_root = Path.cwd()

    if convention_path is None:
        convention_path = _CONVENTION_PATH

    patterns = _load_registry(convention_path)
    audit_file = repo_root / _AUDIT_LOG_RELPATH
    state_file = repo_root / _LOOP_STATE_RELPATH

    decision: Decision = Decision(action="allow")

    for pattern in patterns:
        match_spec = pattern.get("match", {})
        if not _matches(command, match_spec):
            continue

        rule_id: str = pattern["id"]
        reason: str = pattern.get("reason", "").strip()
        alternative: str = pattern.get("alternative", "").strip()
        match_type: str = pattern.get("match_type", "hard_block")

        if match_type == "hard_block":
            decision = Decision(
                action="block",
                rule_id=rule_id,
                reason=reason,
                alternative=alternative,
            )
            break

        if match_type == "loop_block":
            loop_cfg = pattern.get("loop_detection", {})
            threshold: int = int(loop_cfg.get("threshold", 1))
            ttl: int = int(loop_cfg.get("ttl_seconds", 60))

            if _is_loop_command(command) or _check_and_record_loop_call(
                rule_id, threshold, ttl, state_file
            ):
                decision = Decision(
                    action="block",
                    rule_id=rule_id,
                    reason=reason,
                    alternative=alternative,
                )
            else:
                decision = Decision(action="allow", rule_id=rule_id)
            break

    _write_audit(command, tool, decision, audit_file)
    return decision


# ---------------------------------------------------------------------------
# Hook entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """Entry point for the claude-pre-tool-use hook.

    Usage: python3 forbidden_command_classifier.py <repo_root>
    Reads Claude Code JSON payload from stdin.
    Prints "block\\n<rule_id>\\n<reason>\\n<alternative>" or "allow" to stdout.
    """
    import sys

    repo_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    try:
        raw = sys.stdin.read()
        payload: dict = json.loads(raw) if raw.strip() else {}
        tool_name: str = payload.get("tool_name", "")
        if tool_name != "Bash":
            print("allow")
            sys.exit(0)
        command_str: str = (payload.get("tool_input") or {}).get("command", "")
        if not command_str:
            print("allow")
            sys.exit(0)
        d = classify(command_str, tool="Bash", repo_root=repo_root)
        if d.action == "block":
            print(f"block\n{d.rule_id or ''}\n{d.reason or ''}\n{d.alternative or ''}")
        else:
            print("allow")
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) Classifier crash must not DoS the hook; fail open with stderr warning
        sys.stderr.write(f"ATDD: forbidden-command classifier error (fail open): {exc}\n")
        print("allow")
