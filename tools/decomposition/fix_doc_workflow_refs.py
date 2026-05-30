#!/usr/bin/env python3
"""Fix remaining 'workflow' references in the doc that the team's rename pass missed.
Preserves legitimate uses (Temporal's own decorator, GitHub Actions, struct field names)."""
from pathlib import Path

# Portable path resolution: this script lives at tools/decomposition/<name>.py
# So the repo root is two parents up from this file.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DOC = REPO_ROOT / "docs" / "coach-decomposition.md"

# Each (old, new, count_expected) — count helps catch over/under matches.
EDITS = [
    # 1. Executive summary
    ("stateful workflow orchestration",
     "stateful train-runner orchestration", 1),
    # 3.4 CLI surface row
    ("**NEW** — replay a workflow run (added in Child 9)",
     "**NEW** — replay a train run (added in Child 9)", 1),
    # 4.2 TransitionDecision comment
    ("verdict: Verdict             # PROCEED ⇒ dispatch; others ⇒ workflow surfaces",
     "verdict: Verdict             # PROCEED ⇒ dispatch; others ⇒ train runner surfaces", 1),
    # 4.4 file path comment
    ("```python\n# atdd/workflow/persistence.py\ndef load_conventions",
     "```python\n# atdd/train/persistence.py\ndef load_conventions", 1),
    # 4.6 file path comment
    ("```python\n# atdd/workflow/persistence.py\n\nclass PersistenceStore(Protocol):",
     "```python\n# atdd/train/persistence.py\n\nclass PersistenceStore(Protocol):", 1),
    # 4.7 runner_iface file path
    ("```python\n# atdd/workflow/runner_iface.py\n\nclass TrainRunner(Protocol):",
     "```python\n# atdd/train/runner_iface.py\n\nclass TrainRunner(Protocol):", 1),
    # 4.7 helper-types location comment block
    ("#   RunId, RunStatus, RunSummary, RunState, WaveResult, TrainEvent → atdd/workflow/types.py\n#   IssueRecord → atdd/workflow/persistence.py",
     "#   RunId, RunStatus, RunSummary, RunState, WaveResult, TrainEvent → atdd/train/types.py\n#   IssueRecord → atdd/train/persistence.py", 1),
    # 4.8 DispatchSpec docstring
    ("\"\"\"The typed handoff between workflow (decided what) and runtime (do it).",
     "\"\"\"The typed handoff between train runner (decided what) and runtime (do it).", 1),
    # 4.8 DispatchSpec prompt_text comment
    ("prompt_text: str             # FULLY RENDERED — workflow did template substitution",
     "prompt_text: str             # FULLY RENDERED — train runner did template substitution", 1),
    # 5.2 single-writer note above table
    ("Single-writer (workflow). Schema-versioned. Append-only.",
     "Single-writer (train runner). Schema-versioned. Append-only.", 1),
    # 6.1 sequence diagram — workflow.X labels
    ("│ workflow.dispatch  workflow.wait        workflow.surface      │ │",
     "│ train.dispatch     train.wait           train.surface         │ │", 1),
    ("        workflow.cleanup: worktree, surfaces, run dir snapshot",
     "        train.cleanup: worktree, surfaces, run dir snapshot", 1),
    # 6.4 agent done signal table
    ("Worker writes a sentinel line to the agent's `events.jsonl`; runtime.agent_control detects via file watcher and forwards to workflow event loop",
     "Worker writes a sentinel line to the agent's `events.jsonl`; runtime.agent_control detects via file watcher and forwards to train-runner event loop", 1),
    # 7.4 YAML config root key
    ("# .atdd/config.yaml\nworkflow:\n  runner: jsonl",
     "# .atdd/config.yaml\ntrain:\n  runner: jsonl", 1),
    # 9 incident defenses I-5
    ("`coach.core.next_transition` (returns Persona) + `workflow.dispatch` (asserts spec.persona matches decision.persona)",
     "`coach.core.next_transition` (returns Persona) + `train.dispatch` (asserts spec.persona matches decision.persona)", 1),
    # 9 incident defenses I-7
    ("| I-7 | No-progress TTL | Stuck workflow burns infinite time |",
     "| I-7 | No-progress TTL | Stuck run burns infinite time |", 1),
    # 13.3 (Child 3) scope file path
    ("- Create `src/atdd/workflow/persistence.py` with the `PersistenceStore` Protocol (signatures only; first impl ships in Child 7).",
     "- Create `src/atdd/train/persistence.py` with the `PersistenceStore` Protocol (signatures only; first impl ships in Child 7).", 1),
    # 13.5 (Child 5) blocks-on annotation
    ("**Blocks:** Child 7 (workflow uses worktree)",
     "**Blocks:** Child 7 (train runner uses worktree)", 1),
    # 13.7 (Child 7) out-of-scope
    ("- The actual workflow runner (Child 8).",
     "- The actual train runner (Child 8).", 1),
    # 13.8 (Child 8) scope file path
    ("- Create `src/atdd/workflow/runner_iface.py` with `TrainRunner` Protocol and `PolicyHandle` per §4.7.",
     "- Create `src/atdd/train/runner_iface.py` with `TrainRunner` Protocol and `PolicyHandle` per §4.7.", 1),
    # 17 Glossary — DispatchSpec
    ("| **DispatchSpec** | Typed handoff from workflow to runtime to spawn a worker |",
     "| **DispatchSpec** | Typed handoff from train runner to runtime to spawn a worker |", 1),
    # 17 Glossary — events.jsonl
    ("| **events.jsonl** | Single-writer (workflow) append-only event log |",
     "| **events.jsonl** | Single-writer (train runner) append-only event log |", 1),
    # 20.4 handoff data table
    ("| **Per-run events** | `.atdd/runtime/runs/<run_id>/events.jsonl` (after #894) | Workflow runner (single-writer) |",
     "| **Per-run events** | `.atdd/runtime/runs/<run_id>/events.jsonl` (after #894) | TrainRunner (single-writer) |", 1),
]

text = DOC.read_text()
report = []
for old, new, expected in EDITS:
    actual = text.count(old)
    if actual == 0:
        report.append(f"⚠ NOT FOUND: {old[:80]}...")
        continue
    if actual != expected:
        report.append(f"⚠ COUNT MISMATCH (found {actual}, expected {expected}): {old[:80]}...")
    text = text.replace(old, new, expected)
    report.append(f"✓ replaced ({actual}x): {old[:60]}...")

DOC.write_text(text)
for r in report:
    print(r)
print(f"\n{sum(1 for r in report if r.startswith('✓'))} edits applied, {sum(1 for r in report if r.startswith('⚠'))} warnings")
