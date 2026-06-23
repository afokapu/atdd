# Convention-graph validators

13 graph-question families / 22 reusable templates under
`src/atdd/validators/conventions/<family>/`. Each family asks one class of
executable question against the composed convention graph. Runs in parallel
with the legacy persona validators until parity (#1205/#1206) permits
decommissioning (#1207). See `registry.yaml` for the catalogue and each
family `README.md` for its question shapes.
