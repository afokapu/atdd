"""GREEN fixture root (composition.py is a graph root by convention).

Imports service -> service is reachable -> RAW = [] -> strict disposition PASS.
(Named composition.py, not test_*.py/conftest.py, so the provider's own pytest
run does not collect the fixture as a test.)
"""
from service import run


def wire():
    return run
