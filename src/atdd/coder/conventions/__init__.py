"""Package marker for the coder convention catalogue (#1868).

Not an import surface — the contents are YAML the validators read as data. This
file exists so that `conventions/tests/` is named `atdd.coder.conventions.tests.*`
rather than under the top-level `tests` namespace, where it collided with the root
`tests/` package and aborted collection of the whole configured suite.
"""
