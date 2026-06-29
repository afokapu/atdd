# Provider conformance suite — `atdd.workspace.python-pytest`

These tests assert that this provider satisfies the **workspace-provider contract**
(`contract_version: 1.0.0`): it discovers `atdd.implementation.yaml` units, runs
them with the declared command, and emits results in the ATDD violation-output
contract (`rule_id` + location).

A new runtime that wants to offer the same contract (e.g.
`atdd.workspace.node-vitest`, `atdd.workspace.go-test`) proves equivalence by
passing an equivalent conformance suite. Conformance tests stay **with the
provider**, never inside the extensions that consume it.

## Running it

The suite is a **real** pytest run (it executes nested pytest subprocesses to
prove the run→violation translation), not a stub:

```bash
pip install pytest pyyaml
pytest official/atdd.workspace.python-pytest/conformance/
```

`test_provider_contract.py` covers both halves of the contract:

- **discover** — `discover_implementations` returns only contract-compatible
  `atdd.implementation.yaml` units; skips malformed / wrong-kind / wrong-major
  manifests; plus the `contract_compatible` SemVer table.
- **run** — `run_implementation` executes pytest and maps a passing run to zero
  violations and a failing run to one violation keyed by `rule_id`
  (implementation id).

CI runs this on every push/PR via the `provider-conformance` job in
`.github/workflows/validate-packages.yml`.
