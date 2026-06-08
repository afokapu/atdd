"""Pure danger-action rules (no I/O).

Two layers, both used by the safety gate BEFORE the coach is ever consulted:

1. ``match_danger`` — an explicit danger fast-path: a substring denylist of
   work-destroying git/fs/db operations. Used on prose (decision-option labels,
   confirm-block prompts) where the danger is whether the *text describes* a
   destructive action (WMBT C002/C005).

2. ``classify_command`` — an **allowlist** command gate for a shell command's
   tool_input (WMBT C003). A denylist can never be complete, so its default of
   ``auto`` silently auto-approved the long tail of mutating commands (#1014).
   The safe posture inverts that: ``auto`` ONLY for a known read-only allowlist,
   ``human_required`` for every danger-pattern match AND every unrecognized
   command (escalate-by-default).
"""
from __future__ import annotations

from typing import Optional

AUTO = "auto"
HUMAN_REQUIRED = "human_required"

# Explicit danger fast-path. Substring, case-insensitive. Note ``-D`` lowercases
# to ``-d`` so ``git branch -d`` catches both the merged-delete and the
# force-delete (``-D``) forms — both discard a ref. Patterns are anchored to a
# command token (e.g. ``dd if=`` not bare ``dd``) so they do not false-positive
# on prose like the word "add".
DANGER_PATTERNS = (
    # --- original set ---
    "git push",
    "force push",
    "git push --force",
    "git merge",
    "gh pr merge",
    "rm -rf",
    "drop table",
    "destructive migration",
    "force-push",
    # --- git: discard work / delete refs (#1014) ---
    "git reset --hard",
    "git clean",            # -f/-fd/-x — bare `git clean` refuses, escalate anyway
    "git branch -d",        # also matches -D after lowercasing
    "git checkout --force",
    "git checkout -f",
    "git checkout .",
    "git restore",
    "git stash drop",
    "git stash clear",
    "git rebase",
    "git update-ref -d",
    "git reflog expire",
    "git filter-branch",
    "git gc --prune",
    # --- filesystem / datastore (#1014) ---
    "delete from",
    "truncate table",
    "dd if=",
    "mkfs",
    "chmod -r",
    "truncate -s",
    "kill -9",
    "shutdown",
)

# Known-safe read-only commands. A tool_input whose leading token(s) match one of
# these — and that carries no shell-composition metacharacter — is auto-approved.
# Everything else escalates. Keep this list read-only ONLY: adding a mutating
# command here re-opens the #1014 hole.
READONLY_ALLOWLIST = (
    ("git", "status"),
    ("git", "log"),
    ("git", "diff"),
    ("git", "show"),
    ("ls",),
    ("cat",),
    ("head",),
    ("tail",),
    ("grep",),
    ("rg",),
    ("find",),
    ("echo",),
    ("pwd",),
    ("which",),
    ("pytest",),
    ("atdd", "validate"),
    ("atdd", "gate"),
)

# Shell metacharacters that can chain, redirect, or substitute a second command.
# Their presence disqualifies a command from the read-only allowlist — a leading
# ``ls`` says nothing about what follows ``;`` or ``&&`` — so it escalates.
_SHELL_COMPOSE = (";", "&&", "||", "|", ">", "<", "`", "$(", "\n")

# ``find`` is read-only EXCEPT for these action predicates, which mutate.
_FIND_MUTATING = ("-delete", "-exec", "-execdir")


def match_danger(text: str) -> Optional[str]:
    """Return the first danger pattern found in ``text`` (case-insensitive), or None."""
    if not text:
        return None
    low = text.lower()
    for pattern in DANGER_PATTERNS:
        if pattern in low:
            return pattern
    return None


def is_readonly_safe(text: str) -> bool:
    """True iff ``text`` is a single known read-only command with no shell
    composition. Conservative: anything it cannot positively recognize is False
    (so the caller escalates)."""
    if not text:
        return False
    stripped = text.strip()
    if any(meta in stripped for meta in _SHELL_COMPOSE):
        return False
    tokens = [t.lower() for t in stripped.split()]
    if not tokens:
        return False
    for entry in READONLY_ALLOWLIST:
        n = len(entry)
        if tuple(tokens[:n]) == entry:
            if entry == ("find",) and any(flag in tokens for flag in _FIND_MUTATING):
                return False
            return True
    return False


def classify_command(text: str) -> str:
    """Allowlist command gate (escalate-by-default, WMBT C003).

    ``human_required`` for any danger-pattern match OR any command not on the
    read-only allowlist; ``auto`` only for a recognized read-only command.
    """
    if match_danger(text) is not None:
        return HUMAN_REQUIRED
    if is_readonly_safe(text):
        return AUTO
    return HUMAN_REQUIRED
