"""Block-grammar value objects for a modular decision document (pure, no I/O).

Mirrors the block grammar added to ``commons:decision:request``: a decision is a
COMPOSITION of blocks (a document), not a fixed single-question shape. Each
``Block`` is one modular unit of the grammar — ``single_choice`` (pick one),
``multi_choice`` (pick 0..N; covers checkbox/multi-select), ``free_text`` (type
an answer), ``confirm`` (approve/deny; covers permission), ``group`` (compose
child blocks). A ``DecisionDocument`` is the ordered tuple of blocks.

The answer side mirrors the question side: one ``BlockAnswer`` per block (a
single option for single_choice, a list for multi_choice, text for free_text, a
decision for confirm), composed into a ``DecisionAnswer``. Every block carries
its chosen ``Option`` objects (id + label) so the contract side can read the ids
while the cmux reply side reads the labels — no downstream id→label resolution.

All frozen and built only from plain data, so the mapper / decider / reply
mapper stay unit-testable without any cmux dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    Option,
)

# block kinds — the contract grammar. multi_choice covers checkbox/multi-select;
# confirm covers permission/approve-deny.
SINGLE_CHOICE = "single_choice"
MULTI_CHOICE = "multi_choice"
FREE_TEXT = "free_text"
CONFIRM = "confirm"
GROUP = "group"

# confirm-block decisions
APPROVE = "approve"
DENY = "deny"


@dataclass(frozen=True)
class Block:
    """One modular unit of a decision document."""

    block_id: str
    kind: str
    prompt: str
    header: Optional[str] = None
    options: Tuple[Option, ...] = ()
    min_selections: Optional[int] = None
    max_selections: Optional[int] = None
    blocks: Tuple["Block", ...] = ()  # children, when kind == GROUP


def _iter_leaf_blocks(blocks: Tuple[Block, ...]):
    """Yield every answerable leaf block, descending into groups in order."""
    for block in blocks:
        if block.kind == GROUP:
            yield from _iter_leaf_blocks(block.blocks)
        else:
            yield block


@dataclass(frozen=True)
class DecisionDocument:
    """An ordered composition of blocks — the full decision, not flattened."""

    blocks: Tuple[Block, ...]

    def block_ids(self) -> Tuple[str, ...]:
        return tuple(b.block_id for b in self.blocks)

    def leaf_blocks(self) -> Tuple[Block, ...]:
        """Every answerable leaf block, descending into groups in document order.

        The single traversal both the decider (render + answer every block) and
        the safety gate (scan for a dangerous block) share, so group composition
        is flattened identically everywhere.
        """
        return tuple(_iter_leaf_blocks(self.blocks))


@dataclass(frozen=True)
class BlockAnswer:
    """The answer to one block, of that block's kind."""

    block_id: str
    kind: str
    selected: Tuple[Option, ...] = ()  # single/multi choice (id + label)
    text: Optional[str] = None  # free_text
    decision: Optional[str] = None  # confirm: APPROVE | DENY


@dataclass(frozen=True)
class DecisionAnswer:
    """The composed answer to a decision document — one BlockAnswer per block."""

    answers: Tuple[BlockAnswer, ...] = field(default_factory=tuple)

    def for_block(self, block_id: str) -> Optional[BlockAnswer]:
        for a in self.answers:
            if a.block_id == block_id:
                return a
        return None
