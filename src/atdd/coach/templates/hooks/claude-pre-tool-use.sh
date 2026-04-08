#!/bin/sh
# Periodic commit reminder for AI agent workflows.
# Install: cp this to .claude/hooks/pre_tool_use.sh
#
# Claude Code runs this before each tool use. If >5 files are modified
# since the last commit, it prints a reminder to stderr (advisory only).

MODIFIED=$(git diff --name-only 2>/dev/null | wc -l | tr -d ' ')
if [ "$MODIFIED" -gt 5 ]; then
    echo "ATDD REMINDER: $MODIFIED files modified since last commit. Consider committing before continuing." >&2
fi
