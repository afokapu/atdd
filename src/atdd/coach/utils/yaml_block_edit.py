"""Edit one top-level block of a YAML document without touching the rest (#1455).

`.atdd/config.yaml` is an operator-facing file: it carries section comments,
trailing annotations and deliberate blank lines. Four writers in
`initializer.py` load it with `yaml.safe_load` and write it back with
`yaml.dump`, and that round-trip cannot preserve any of them — PyYAML discards
comments at parse, so they are gone before the dump is reached. A substrate or
GitHub-bootstrap write therefore drops whatever the operator wrote, silently.

Every one of those writers mutates exactly ONE top-level key (`repo`,
`github`), so the round-trip was never needed. These helpers rewrite only that
key's block in the source text and leave every other byte alone, which is
stronger than a round-trip can be: bytes outside the target block are not
re-serialised at all, so nothing can be lost by a formatting difference.

`ruamel.yaml` would preserve comments through a round-trip, but this project
ships PyYAML and adding a dependency to write one key is disproportionate.

SCOPE. Top-level keys only, block style only — which is what `.atdd/config.yaml`
is and what the callers need. A document whose target key is written inline
(`repo: {a: 1}`) is handled: the single line is replaced. Anything more exotic
is out of scope rather than silently mishandled, so callers keep using the
round-trip where the whole document is being created from nothing
(`_create_config`), which has no comments to lose.
"""
from __future__ import annotations

import re
from typing import Any, List

import yaml

__all__ = ["set_top_level_block", "remove_top_level_block"]


def _key_pattern(key: str) -> "re.Pattern[str]":
    """Matches the start of *key*'s top-level block: column zero, then a colon."""
    return re.compile(rf"^{re.escape(key)}\s*:", re.M)


def _block_bounds(lines: List[str], key: str) -> "tuple[int, int] | None":
    """``(start, end)`` line indices of *key*'s block, or ``None`` if absent.

    ``end`` is exclusive and stops at the next column-zero key or end of file, so
    an indented child of the block is included and a following sibling is not.
    """
    pat = _key_pattern(key)
    start = next((i for i, l in enumerate(lines) if pat.match(l)), None)
    if start is None:
        return None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.strip() and not line[0].isspace() and not line.lstrip().startswith("#"):
            end = i
            break
    return start, end


def _render(key: str, value: Any) -> List[str]:
    """*key* and *value* as block-style YAML lines, without a document marker."""
    text = yaml.safe_dump({key: value}, default_flow_style=False, sort_keys=False)
    return text.rstrip("\n").split("\n")


def set_top_level_block(source: str, key: str, value: Any) -> str:
    """Return *source* with *key* set to *value*, every other byte unchanged.

    Replaces the key's existing block in place when present — so a comment
    written above it stays above it — and appends otherwise.
    """
    lines = source.split("\n")
    trailing_newline = source.endswith("\n")
    if trailing_newline:
        lines = lines[:-1]

    rendered = _render(key, value)
    bounds = _block_bounds(lines, key)
    if bounds is None:
        # No blank separator. Appending one but not adding it on a later replace
        # made the result depend on whether the key already existed, so a repeated
        # `atdd init --force` produced two different files and its idempotency
        # assertion failed. Output now depends only on (source, key, value).
        lines.extend(rendered)
    else:
        start, end = bounds
        lines[start:end] = rendered

    out = "\n".join(lines)
    return out + "\n" if trailing_newline else out


def remove_top_level_block(source: str, key: str) -> str:
    """Return *source* with *key*'s block removed, or unchanged if absent.

    A comment sitting above the block is left in place: it is the operator's
    line, and this function cannot know it described only the removed key.
    """
    lines = source.split("\n")
    trailing_newline = source.endswith("\n")
    if trailing_newline:
        lines = lines[:-1]

    bounds = _block_bounds(lines, key)
    if bounds is None:
        return source

    start, end = bounds
    del lines[start:end]
    out = "\n".join(lines)
    return out + "\n" if trailing_newline else out
