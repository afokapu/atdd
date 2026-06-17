# `atdd.workspace.cmux-claude` — Workspace Provider Boundary Specification

> **Issue #1120 (Slice 3 of #1113).** Backlog materialization. Specifies the
> **workspace-provider** boundary (NOT an extension). Moves no conventions, changes no
> core, implements no runtime. Source rows from
> `docs/coach-convention-decomposition-plan.md` (PR #1115).

## 1. Identity (workspace-shaped)

```yaml
workspace_id: atdd.workspace.cmux-claude
kind: workspace
contract_version: "1.0.0"     # the agent-session launch + transport contract
runtime:
  multiplexer: cmux
  agent: claude
  capability: agent-session-transport
```

Provides **runtime transport** for agent sessions — launch, decision/correction
delivery, session presentation. No domain behavior; no `owns: {conventions}`.

## 2. What it provides

- cmux-native launch (claude positional-prompt first turn) + the freedom-set flags.
- The Feed transport that surfaces worker decisions, and the `cli-return.jsonl` correction
  inbox — the *channels* the core mediation/correction *requirements* ride on.
- Session naming/grid-layout drift correction; the bash-prompt classifier; `atdd spawn`.

## 3. Source rows → workspace material

| source_file | section | becomes |
|-------------|---------|---------|
| `coach.convention.yaml` | activation / launch_transport / observer_corrections transport | launch + transport runtime |
| `session.convention.yaml` | freedom tables / naming / layout / multiplexer / launch-prompt | runtime config + drift correctors |
| `observer.convention.yaml` | bash_classifier / token_threshold / drift rules | runtime correctors |
| `spawn.convention.yaml` | `coach.spawn.atdd-spawn-cli` | launch entry implementation |
| `forbidden_commands.convention.yaml` | `ATDD-FORBID-CMUX-SEND-CLAUDE` | command-policy pattern |

## 4. Owns / does not own

**Owns:** the launch/transport runtime contract; cmux/Claude execution mechanics;
conformance proving an alternate transport (zellij/tmux, another LLM) satisfies the same
contract.

**Does not own:** the *requirement* that decisions are mediated and corrections are
structured — those stay core (`coach.execution.decisions-mediated-not-auto-executed`,
`coach.execution.freedom-with-a-leash`, `coach.execution.structured-correction-and-escalation`).
This workspace only carries them on a concrete transport.

## 5. Graph Context

No convention nodes, no relationship-graph change. Provider-local relationships would live
in `atdd.workspace.cmux-claude.relationships`; core-graph composition deferred (#1122).
If Claude later needs decoupling from cmux, split the package then — not now.

## 6. Acceptance

- [ ] workspace-provider boundary specified (manifest is workspace-shaped)
- [ ] source rows mapped
- [ ] no core files changed; no runtime implemented (stub/deferred)
- [ ] core mediation/correction requirements explicitly left in core
