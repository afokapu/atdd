# mirror-coverage

Twin coverage of the core coder/tester convention surface — the measurement #1714's
classification gate rests on and #1993 named as its ready-to-start condition.

```
python3 tools/mirror-coverage/coverage.py                   # report, by family
python3 tools/mirror-coverage/coverage.py --json            # machine-readable
python3 tools/mirror-coverage/coverage.py --classification <record.md>
```

Exits **0** only when every core coder/tester rule is covered — either an extension
node mirrors it, or the classification record carries a why-not verdict for it.
Exits **1** otherwise, naming the shortfall by family.

It computes nothing itself. Every figure comes from
`atdd.enforce.twin_coverage`, the shipped measure pinned by
`wmbt:govern-registry:E003`; this script only adds a report and an exit code. A
second implementation of the measurement would be a second answer to drift from,
which is the failure mode this whole program is about — so if you need the number in
code, import the module rather than copying from here.

Two readers in that module are load-bearing and each has a wrong twin that passes
silently. Provenance must be read off the extension node document
(`iter_extension_nodes`), never the flat single-node rule projection, which drops
`source`. The core surface must be walked by `extract_rules`, which recurses into
nested `rules:` lists. Do not reach for `.carve-lab/inventory.py`: its depth-1 YAML
reader misses them and understates the corpus. Both traps are pinned by
E003-UNIT-002 and E003-UNIT-003.
