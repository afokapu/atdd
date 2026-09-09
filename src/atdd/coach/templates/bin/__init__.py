"""Package marker for the coach template bin directory (#1868).

Not an import surface — the contents are shipped template scripts. This file
exists so that `bin/tests/` is named `atdd.coach.templates.bin.tests.*` rather
than under the top-level `tests` namespace, where it collided with the root
`tests/` package and aborted collection of the whole configured suite.
"""
