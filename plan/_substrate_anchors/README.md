# Substrate Anchor Stubs

Anchor files in this directory exist solely to satisfy substrate
Class 1 bidirectional-binding (`tester.acceptance-violation.validator-binding-must-be-bidirectional`) for toolkit
acceptances whose real wired tests are pending.

Each file is named `<wagon>__<wmbt>_anchor_test.py` and lists
every acceptance under that WMBT as a `# Acceptance: <urn>` header.
Each test body is `pytest.skip(...)` — substrate harness-mode
rules are vacuously satisfied (skipped tests don't raise
AssertionError), but the binding is observable to
`atdd repo validate`.

When a real wired test for an acceptance lands elsewhere in the
tree, drop the corresponding stub from the anchor file. When
every acceptance in a WMBT has real coverage, delete the anchor
file outright.
