"""Convention graph root that keeps the scan live (composition.py).

Imports NOTHING in this tree, so it reaches only itself. app.py / lib.py are
therefore reachable ONLY via the pyproject entry point (app.py), supplied to the
detector through ATDD_GRAPH_ROOTS. Named composition.py (not test_*.py/conftest.py)
so the provider's own pytest run does not collect the fixture as a test, and there
is no ``src/`` sibling subtree so it grants no implicit reach.
"""


def wire():
    return None
