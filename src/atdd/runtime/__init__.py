"""``atdd.runtime`` — execution layer for the Coach decomposition.

Sub-layers (docs/coach-decomposition.md §3.1):

* ``atdd.runtime.agent_control`` — worker spawn (shim), prompt delivery, ready
  detection, correction inbox, stdin forwarding, agent done signals, transport
  selection. The default control plane is cli-return.
* ``atdd.runtime.multiplexer`` — view-only surface CREATE / ATTACH / CLOSE for
  observability. NO control methods (§4.9).
* ``atdd.runtime.worktree`` — git worktree lifecycle + branch safety (Child 5).

Per §3.3 these layers import only stdlib (+ subprocess); they MUST NOT import
``atdd.coach.*``, ``atdd.train.*``, ``atdd.integrations.*``, and the
agent_control / multiplexer siblings MUST NOT import each other.
"""
