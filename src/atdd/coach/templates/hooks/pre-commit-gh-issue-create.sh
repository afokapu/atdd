#!/bin/sh
# ATDD L3b pre-commit hook for `gh issue create` (issue #816).
#
# Installed by `atdd init`. Greps the staged diff for *added* lines that bake a
# `gh issue create` call into committed source, and rejects the commit with an
# educational pointer to `atdd author issue`. Markdown files (*.md) are exempt so docs
# may quote the forbidden command in code fences.
#
# This is a standalone, fully-functional pre-commit hook — it may be installed
# directly as .git/hooks/pre-commit or chained from an aggregating hook.

set -e

# Staged files this commit touches, excluding markdown docs.
files=$(git diff --cached --name-only --diff-filter=ACM | grep -v '\.md$' || true)
[ -z "$files" ] && exit 0

# Added lines (^\+ anchor — removals are exempt) that invoke `gh issue create`.
# Word boundaries keep `gh issuecreated` and similar near-misses from matching.
hits=$(
    git diff --cached --unified=0 -- $files \
        | grep -E '^\+.*\bgh[[:space:]]+issue[[:space:]]+create\b' \
        || true
)

if [ -n "$hits" ]; then
    cat >&2 <<'EOF'

ATDD: `gh issue create` found in staged changes — commit blocked.

GitHub issues must be created through the toolkit so they are registered in the
manifest and the project board. Do not bake `gh issue create` into source.

  Use:  atdd author issue --title <title> --slug <slug>

(Markdown docs are exempt; this guard only flags executable/source files.)
EOF
    exit 1
fi

exit 0
