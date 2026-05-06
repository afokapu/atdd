# URN: component:govern-lifecycle:enforcement-substrate:spawn_harness:backend:domain
# Runtime: python
# Purpose: Coach spawn-harness renderer that emits repo-rule blocks (wmbt/train/security) into spawn prompts per substrate spec v12 §8.2.

"""Coach v6 spawn-harness — substrate extensions (issue #417).

Coach v6 §7.1 spawns coder/tester subagents with a prompt that includes a
``conventions[].rules_in_scope`` block listing toolkit convention rules in
play for the current phase. The substrate (spec v12 §8.2) extends that
prompt with three parallel blocks for repo-derived rules:

* ``wmbt_rules:``     — WMBT acceptances whose ``RuleMetadata.phase`` matches
                        the current coach phase.
* ``train_rules:``    — Train acceptances whose ``RuleMetadata.phase`` matches
                        the current coach phase.
* ``security_rules:`` — Security rules whose BOUND acceptance's phase matches
                        the current coach phase (full filter wires up in #422;
                        this PR emits the block shape with a TODO).

The renderer is registry-driven: callers pass a sequence of
``RuleMetadata`` instances (typically the output of
``rule_binding.iter_rules()`` or a hand-built fixture for tests). The
output is YAML emitted in the spec §8.2 verbatim shape.
"""
from atdd.coach.spawn_harness.renderer import (
    render_spawn_blocks,
    render_security_rules_block,
    render_train_rules_block,
    render_wmbt_rules_block,
)

__all__ = [
    "render_spawn_blocks",
    "render_security_rules_block",
    "render_train_rules_block",
    "render_wmbt_rules_block",
]
