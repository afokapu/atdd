"""``atdd.runtime`` — execution layer for the Coach decomposition.

Sub-layers (docs/coach-decomposition.md §3.1):

* ``atdd.runtime.worktree`` — git worktree lifecycle + branch safety (Child 5).

The ``agent_control`` and ``multiplexer`` sub-layers were pruned by #1480: core
coach is lifecycle governance and does not manage sub-workers, so the
worker-dispatch control plane and the view-only surface Protocol were removed
outright rather than relocated.

Per §3.3 this layer imports only stdlib (+ subprocess); it MUST NOT import
``atdd.coach.*``, ``atdd.train.*`` or ``atdd.integrations.*``.
"""
