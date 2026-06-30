"""The pyproject ``[project.scripts]`` entry-point module.

No convention root imports this and it is not a root by name, so without its path
in ATDD_GRAPH_ROOTS it is unreachable -> falsely flagged dead. Core resolves it
from ``[project.scripts]`` and forwards its absolute path; the detector then unions
it into the graph roots, and it (plus lib.py, which only it imports) becomes
reachable -> NOT flagged. Mirrors legacy find_cli_entry_points().
"""
from lib import helper


def cli():
    return helper()
