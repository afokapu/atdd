# URN: component:govern-lifecycle:enforcement-substrate:metrics:backend:domain
# Runtime: python
# Purpose: Toolkit-shipped commons for the metric-function registry (spec v12 §4.5).

"""Toolkit-shipped metric implementations.

Each module under this package exposes:

    def compute(repo_root: Path) -> int | float | bool: ...
    def passes(value, threshold) -> bool: ...

The metric runner (``atdd.runners.metric_runner``) discovers metrics via a
two-root walk: a repo-local override at ``<repo>/.atdd/metrics/<name>.py``
takes precedence over the toolkit-shipped module at
``atdd/runners/metrics/<name>.py``.

This package starts empty; toolkit commons such as ``lines_of_code`` or
``cyclomatic_complexity`` are added as separate substrate issues.
"""
