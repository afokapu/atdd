"""Pure terminal-text -> DecisionPrompt parser (no I/O).

Deliberately conservative: it emits a prompt only when the tail of the surface
contains a recognizable option list, and it always picks the *latest* such list
(WMBT L001). Non-decision output — empty buffers, progress bars, half-rendered
prompts missing their options — yield ``None`` so the bridge never routes a
false decision request (WMBT C001).

ANSI stripping and buffer assembly are the integration adapter's job; this
function takes already-plain ``str`` so it is fully deterministic and unit-pure.
"""
from __future__ import annotations

import re
from typing import List, Optional

from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    DecisionPrompt,
    Option,
)

# An option line: "1) ...", "1. ...", "2: ...", "[3] ...", "a) ...", "- ..." with a label.
_OPTION_RE = re.compile(r"^\s*\[?([0-9]+|[A-Za-z])\]?[\.\):\-]\s+(\S.*)$")
_TAIL_LINES = 80


def parse_prompt(text: str) -> Optional[DecisionPrompt]:
    """Extract the latest decision prompt from surface ``text``, or ``None``."""
    if not text or not text.strip():
        return None

    lines = [ln.rstrip() for ln in text.splitlines()]
    option_idxs = [i for i, ln in enumerate(lines) if _OPTION_RE.match(ln)]
    if not option_idxs:
        return None

    # Walk up from the last option line, collecting the latest contiguous block
    # (blank lines between options are tolerated; the first non-blank, non-option
    # line above the block is the question).
    last = option_idxs[-1]
    block: List[int] = []
    i = last
    while i >= 0:
        ln = lines[i]
        if _OPTION_RE.match(ln):
            block.append(i)
            i -= 1
        elif ln.strip() == "":
            i -= 1
        else:
            break
    block.reverse()

    options = tuple(_to_option(lines[i]) for i in block)
    # A single bullet is more likely a list item than a decision; require >= 2.
    if len(options) < 2:
        return None

    question = _find_question(lines, block[0])
    raw_text = "\n".join(lines[-_TAIL_LINES:]).strip()
    return DecisionPrompt(raw_text=raw_text, question=question, options=options)


def _to_option(line: str) -> Option:
    m = _OPTION_RE.match(line)
    assert m is not None  # caller guarantees a match
    return Option(id=m.group(1), label=m.group(2).strip())


def _find_question(lines: List[str], block_start: int) -> str:
    """Nearest non-blank, non-option line above the option block."""
    for i in range(block_start - 1, -1, -1):
        ln = lines[i].strip()
        if ln and not _OPTION_RE.match(lines[i]):
            return ln
    return "Worker is requesting a decision."
