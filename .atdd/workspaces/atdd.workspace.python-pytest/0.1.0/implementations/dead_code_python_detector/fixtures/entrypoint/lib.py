"""Reachable ONLY transitively through the entry point app.py.

No convention root reaches lib.py; only app.py imports it. So lib.py is dead
UNLESS app.py is promoted to a graph root via ATDD_GRAPH_ROOTS -- proving the env
contract gates transitive entry-point reach, not just the entry module itself.
"""


def helper():
    return "ok"
