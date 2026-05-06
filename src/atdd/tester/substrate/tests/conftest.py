# URN: component:govern-lifecycle:enforcement-substrate:substrate-plugin-conftest:backend:tests
# Runtime: python
# Purpose: Enable the pytester fixture for substrate-plugin integration tests (issue #411).

"""Conftest for the substrate plugin's own tests.

The plugin's integration tests run an inner pytest process via the
``pytester`` fixture (a fresh sandbox that prevents the outer toolkit
test session from picking up the synthetic test files we generate).
``pytester`` is not enabled by default; activating it here keeps the
opt-in scoped to this directory.
"""

pytest_plugins = ["pytester"]
