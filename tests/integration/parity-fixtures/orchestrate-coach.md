# orchestrate-state.json ↔ decisions.jsonl Mapping

Authoritative oracle for the parity assertions in
`test_orchestrate_coach_parity.py`. Every field in
`orchestrate-state.json` is mapped to its `decisions.jsonl`
counterpart or marked NOT-PRESENT-INTENTIONALLY with rationale.

## orchestrate-state.json Format

```json
{
  "<issue_number>": {
    "worktree_created": true,
    "worktree_path": "/abs/path/to/worktree",
    "launched": true,
    "ref": "workspace:1",
    "mode": "workspace",
    "canonical_name": "ATDD100-single-issue"
  }
}
```

## decisions.jsonl Relevant Records

Two decision types are relevant:

### worktree-create

```json
{
  "decision_id": "<run_id>:#<issue>:worktree-create",
  "decision_type": "worktree-create",
  "issue_number": 100,
  "inputs": {
    "branch": "feat/single-issue",
    "worktree_path": "/abs/path/to/worktree"
  },
  "outcome": {
    "created": true,
    "worktree_path": "/abs/path/to/worktree"
  }
}
```

### agent-spawn

```json
{
  "decision_id": "<run_id>:#<issue>:agent-spawn",
  "decision_type": "agent-spawn",
  "issue_number": 100,
  "inputs": {
    "branch": "feat/single-issue",
    "worktree_path": "/abs/path/to/worktree",
    "canonical_name": "ATDD100-single-issue",
    "multiplexer_mode": "workspace"
  },
  "outcome": {
    "launched": true,
    "ref": "workspace:1",
    "canonical_name": "ATDD100-single-issue"
  }
}
```

## Field Mapping

| orchestrate-state.json field | decisions.jsonl source | Notes |
|---|---|---|
| `worktree_created` | `worktree-create` decision exists for this issue | Boolean equivalence: true ↔ decision exists |
| `worktree_path` | `worktree-create` → `outcome.worktree_path` | Absolute path; compare relative to repo root |
| `launched` | `agent-spawn` decision exists for this issue | Boolean equivalence: true ↔ decision exists |
| `ref` | `agent-spawn` → `outcome.ref` | String equality |
| `mode` | `agent-spawn` → `inputs.multiplexer_mode` | String equality (`"workspace"` or `"pane"`) |
| `canonical_name` | `agent-spawn` → `outcome.canonical_name` | String equality |

## Allowed Differences

The following differences between the two codepaths are explicitly
documented and **do not** constitute parity failures:

1. **State file format**: `orchestrate-state.json` is a single JSON
   document keyed by issue number. `decisions.jsonl` is an append-only
   JSONL file with one record per line. The parity test extracts
   semantically equivalent fields via the mapping above.

2. **Additional logging**: Coach writes `decision_id`, `timestamp`,
   `coach_run_id` fields that have no orchestrate equivalent. These
   are durability metadata, not behavioral outputs.

3. **Additional decision entries**: Coach may record decision types
   beyond `worktree-create` and `agent-spawn` (e.g. `phase-transition`,
   `observer-hookup`). These have no orchestrate equivalent and are
   filtered out during comparison.

4. **Post-launch rename pass**: The orchestrate path calls
   `apply_canonical_name_and_layout()` after each launch, which issues
   `backend.rename()` and `backend.send()` calls. The coach path's
   `phase_b_launch_sessions()` does not issue these calls. The canonical
   name is already passed as the `name` parameter in the
   `new_workspace`/`new_surface` call in both paths, so the naming
   intent is equivalent.

5. **Durability timing**: Orchestrate writes state incrementally after
   each worktree/launch (so partial state persists on crash between
   issues). Coach batches worktree-create decisions and only writes them
   after the entire Phase A loop succeeds (so a mid-loop failure leaves
   zero records). This is a deliberate improvement, not a parity
   violation — the rollback test asserts equivalent *observable*
   behavior (all worktrees removed on failure), not equivalent
   intermediate state.

6. **Timestamp normalisation**: `.launch_prompt.txt` comparison
   normalises ISO-8601 timestamps (`\d{4}-\d{2}-\d{2}T...`) to a fixed
   placeholder before comparing, since the two paths run at different
   wall-clock times.

## Mapping Extraction

The parity test extracts the mapping using:

```python
def _extract_coach_state(decisions):
    """Extract orchestrate-equivalent state from decisions.jsonl records."""
    state = {}
    for rec in decisions:
        num = str(rec["issue_number"])
        if rec["decision_type"] == "worktree-create":
            state.setdefault(num, {})
            state[num]["worktree_created"] = rec["outcome"]["created"]
            state[num]["worktree_path"] = rec["outcome"]["worktree_path"]
        elif rec["decision_type"] == "agent-spawn":
            state.setdefault(num, {})
            state[num]["launched"] = rec["outcome"]["launched"]
            state[num]["ref"] = rec["outcome"]["ref"]
            state[num]["canonical_name"] = rec["outcome"]["canonical_name"]
            state[num]["mode"] = rec["inputs"]["multiplexer_mode"]
    return state
```
