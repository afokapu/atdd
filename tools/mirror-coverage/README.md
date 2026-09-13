# mirror-coverage

Twin coverage of the core coder/tester convention surface — the measurement #1714's
classification gate rests on and #1993 named as its ready-to-start condition.

```
python3 tools/mirror-coverage/coverage.py                   # human-readable
python3 tools/mirror-coverage/coverage.py --json            # machine-readable
python3 tools/mirror-coverage/coverage.py \
    --classification docs/1714-agnostic-mirror-coverage.md  # count why-not rows as covered
```

Exits **0** only when every core coder/tester rule_id either has an extension node
mirroring it or carries a why-not row in the classification record — the no-silent-drop
condition. Exits **1** otherwise, naming the shortfall.

This is a measurement tool, not a gate test: #1714 has no planner artifacts yet, so there
is no acceptance URN a test could bind to (see `docs/1714-agnostic-mirror-coverage.md`,
correction 2). When they exist, the guard moves into `src/atdd/enforce/tests/` under its
acceptance URN and this tool becomes the reproduction aid.

Both surfaces are read through the shipped loader — `extract_rules` for core (it walks
nested `rules:` lists) and `iter_extension_nodes` for provenance (`extract_rules` drops
`source`). Never use `.carve-lab/inventory.py`: its depth-1 YAML reader misses nested
`rules[]` lists and understates the corpus.
