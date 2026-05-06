"""Pytest plugins for atdd toolkit-internal use.

Plugins in this package are loaded via argv injection (``-p
atdd.coach.plugins.<name>``) by the atdd validate runner only. They are
NOT registered via ``pytest_plugins`` or any ``conftest.py``, which would
cause them to auto-load in consumer test suites and leak behavior outside
the validate phase.
"""
