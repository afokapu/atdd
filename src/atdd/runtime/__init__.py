"""ATDD runtime layer — execution adapters (worktree, multiplexer, agent_control).

Per docs/coach-decomposition.md §3.2 / §3.3 the runtime layer owns git worktree
creation, multiplexer surfaces (view-only), and agent control. Each submodule
obeys the dependency rules in §3.3: it may import stdlib + subprocess + pathlib
but MUST NOT import the orchestration (``atdd.train``), policy
(``atdd.coach``), or integration (``atdd.integrations``) layers.
"""
