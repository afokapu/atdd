"""External-system adapters for ATDD (docs/coach-decomposition.md §3.2).

Each integration call returns plain data — never Coach-core types. The
dependency rules in §3.3 forbid this layer from importing ``atdd.coach.*``,
``atdd.train.*``, or ``atdd.runtime.*`` (enforced by
``tests/architecture/test_layer_imports.py``).
"""
