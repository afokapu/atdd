"""Binding-test collection config.

The ``fixtures/`` tree holds real implementation tests that are executed only by
the provider via PROVIDER-SPAWN (a subprocess pytest), never by the main suite —
collecting them here would both duplicate basenames and intentionally error
(``crashing_impl`` raises at import on purpose). Exclude the whole fixtures tree.
"""
collect_ignore_glob = ["fixtures/*"]
