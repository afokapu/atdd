"""Fence-aware access to a work-item body's leading H1 (#1653).

**SHARED SURFACE.** ``#1654`` imports this module rather than re-implementing
H1 parsing, by the ``#1652`` orchestrator ruling: the title/H1 agreement is one
invariant, so it gets one parser. A second, privately-owned regex is exactly how
the two writers drift apart again. A naive ``^# `` match is the specific trap —
it fires inside fenced code blocks, and an ATDD issue body is *full* of fenced
blocks showing shell commands whose lines start with ``#``.

Two facts about the live corpus shape this module (measured over the 822 work
items in the Control Root store, #1653):

- **619 bodies carry no leading H1 at all.** Three bodies in four. Any rule that
  assumes an H1 exists is wrong for the majority, which is why
  :func:`retitle_h1` *never synthesises* one — inventing structure in 619 bodies
  would be a corpus migration wearing a rename's clothes.
- **179 agree with ``data.title``, 24 disagree.** So the divergence this module
  exists to stop is already real, not hypothetical.

Only the *first* H1 outside a fence is meaningful: it is the body's title line.
Later H1s are body structure and are never touched.

Dependency discipline: stdlib only.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

#: A fenced-code-block delimiter: 3+ backticks or 3+ tildes, indented 0-3 spaces
#: (4+ spaces would make it an indented code block, not a fence). Group 1 is the
#: run of fence characters, group 2 the info string.
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*(.*)$")

#: An ATX H1 carrying text: 0-3 spaces, exactly one ``#``, whitespace, content,
#: and CommonMark's optional closing sequence of ``#``s. ``pre``/``post`` are
#: preserved verbatim across a rewrite so only the heading *text* changes.
_H1_RE = re.compile(r"^(?P<pre> {0,3}#[ \t]+)(?P<text>.*?)(?P<post>[ \t]+#+[ \t]*)?$")

#: A bare ``#`` line — a valid, empty ATX H1. It exists, so retitling it is a
#: rewrite rather than a synthesis.
_EMPTY_H1_RE = re.compile(r"^(?P<pre> {0,3})#(?P<post>[ \t]*)$")

#: An ATX heading of level 2+ — matched only so it is never mistaken for an H1.
_DEEPER_HEADING_RE = re.compile(r"^ {0,3}#{2,}(?:[ \t]|$)")


def _is_fence_close(line: str, opener: str) -> bool:
    """True when ``line`` closes a fence opened by ``opener``.

    CommonMark: the closer uses the same character, is at least as long as the
    opener, and carries no info string.
    """
    match = _FENCE_RE.match(line)
    if match is None:
        return False
    run, info = match.group(1), match.group(2)
    return run[0] == opener[0] and len(run) >= len(opener) and not info.strip()


def _find_h1_line(body: Optional[str]) -> Tuple[Optional[int], Optional[re.Match], bool]:
    """Locate the first H1 outside any fence.

    Returns ``(line_index, match, is_empty_heading)``, or ``(None, None, False)``
    when the body has no H1 — the majority case (619 of 822 live bodies).
    """
    if not body:
        return None, None, False
    open_fence: Optional[str] = None
    for index, line in enumerate(body.splitlines()):
        if open_fence is not None:
            if _is_fence_close(line, open_fence):
                open_fence = None
            continue
        fence = _FENCE_RE.match(line)
        if fence is not None:
            open_fence = fence.group(1)
            continue
        if _DEEPER_HEADING_RE.match(line):
            continue
        match = _H1_RE.match(line)
        if match is not None:
            return index, match, False
        match = _EMPTY_H1_RE.match(line)
        if match is not None:
            return index, match, True
    return None, None, False


def first_h1(body: Optional[str]) -> Optional[str]:
    """The text of the body's first ATX H1 outside any fenced code block.

    ``None`` when the body is empty or carries no H1. An empty heading (a bare
    ``#``) reads as ``""`` — it is present, merely blank, and the distinction
    matters to :func:`retitle_h1`.
    """
    _, match, is_empty = _find_h1_line(body)
    if match is None:
        return None
    return "" if is_empty else match.group("text").strip()


def has_h1(body: Optional[str]) -> bool:
    """True when the body carries an H1 outside a fence. False for 619 of 822 live bodies."""
    return _find_h1_line(body)[1] is not None


def retitle_h1(body: Optional[str], title: str) -> Optional[str]:
    """Rewrite the body's leading H1 to ``title``, returning the new body.

    Returns ``body`` **unchanged** when there is no H1 to rewrite. This function
    never synthesises a heading: a body without one keeps its shape, so a title
    rename cannot restructure the 619 bodies that carry no H1 (#1652 ruling (b)).

    Indentation and CommonMark's optional closing ``#`` sequence are preserved,
    so a rewrite touches the heading text and nothing else.
    """
    index, match, is_empty = _find_h1_line(body)
    if match is None or body is None:
        return body
    lines = body.splitlines(keepends=True)
    original = lines[index]
    newline = ""
    for terminator in ("\r\n", "\n", "\r"):
        if original.endswith(terminator):
            newline = terminator
            break
    if is_empty:
        rebuilt = f"{match.group('pre')}# {title}"
    else:
        rebuilt = f"{match.group('pre')}{title}{match.group('post') or ''}"
    lines[index] = rebuilt + newline
    return "".join(lines)


__all__ = ["first_h1", "has_h1", "retitle_h1"]
