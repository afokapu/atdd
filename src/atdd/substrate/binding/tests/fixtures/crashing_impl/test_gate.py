"""A real implementation that CRASHES at collection (import error) — pytest exits
with a usage/collection code, not a clean pass/fail. Stands in for a broken bound
implementation that must fail SAFE to legacy, never silently pass the gate."""
import this_module_does_not_exist  # noqa: F401  -> collection error (exit != 0,1)


def test_never_runs():
    pass
