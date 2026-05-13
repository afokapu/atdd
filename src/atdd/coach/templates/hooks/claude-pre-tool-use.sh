#!/bin/sh
# Pre-tool-use hook for Claude Code agent sessions.
#
# Two guards (additive, both preserved on install):
#   1. Micro-commit reminder: warns when >5 files modified since last commit
#      (advisory only — exits 0, never blocks tool use).
#   2. Forbidden-command classifier: reads forbidden_commands.convention.yaml
#      and exits 2 on HARD-BLOCK or LOOP-BLOCK patterns, with an educational
#      error message naming the atdd-native alternative.
#
# Install:   atdd sync           (canonical install path)
#            cp this to .claude/hooks/pre_tool_use.sh   (manual)
# Source:    src/atdd/coach/templates/hooks/claude-pre-tool-use.sh
# Issue:     #668 (L1 forbidden-command enforcement)

# ── Save stdin once ────────────────────────────────────────────────────────
# Claude Code sends a JSON payload per tool call; we read it here so both
# guards can inspect it without consuming stdin twice.
_HOOK_STDIN=$(cat)

# ── Guard 1: micro-commit reminder (advisory) ──────────────────────────────
MODIFIED=$(git diff --name-only 2>/dev/null | wc -l | tr -d ' ')
if [ "$MODIFIED" -gt 5 ]; then
    echo "ATDD REMINDER: $MODIFIED files modified since last commit. Consider committing before continuing." >&2
fi

# ── Guard 2: forbidden-command classifier ─────────────────────────────────
# Locate the repo root.  ATDD_REPO_ROOT can be set by tests or CI to override
# the git-derived value (e.g. when the hook runs inside a temp repo but the
# classifier lives in the real repo).
_REPO_ROOT="${ATDD_REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null)}"
if [ -z "$_REPO_ROOT" ]; then
    exit 0  # Not in a git repo — skip classifier, allow tool use
fi

_CLASSIFIER="$_REPO_ROOT/src/atdd/coach/utils/forbidden_command_classifier.py"
if [ ! -f "$_CLASSIFIER" ]; then
    exit 0  # Classifier not installed — fail open
fi

# Run the classifier as a script.  It reads the JSON payload from stdin and
# prints "block\n<rule_id>\n<reason>\n<alternative>" or "allow" to stdout.
# The "|| _RESULT=allow" ensures a Python crash never blocks tool use (fail open).
_RESULT=$(printf '%s' "$_HOOK_STDIN" | python3 "$_CLASSIFIER" "$_REPO_ROOT" 2>/dev/null) || _RESULT="allow"

_ACTION=$(printf '%s\n' "$_RESULT" | head -1)
if [ "$_ACTION" = "block" ]; then
    _RULE=$(printf '%s\n' "$_RESULT" | sed -n '2p')
    _REASON=$(printf '%s\n' "$_RESULT" | sed -n '3p')
    _ALT=$(printf '%s\n' "$_RESULT" | sed -n '4p')
    printf 'ATDD BLOCK [%s]: %s\nUse instead: %s\n' "$_RULE" "$_REASON" "$_ALT" >&2
    exit 2
fi
