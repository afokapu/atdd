# Changelog

All notable changes to the ATDD toolkit are documented here.

## [Unreleased]

### Removed

- **`atdd babysit`** — decommissioned in coach v9 (spec §11.3, issue #532).
  Invoking `atdd babysit` now prints a migration message and exits non-zero.
  Original source archived to `commands/_archived/babysit.py` for parity-test
  reuse by the L8 fixture suite (#525).

  **Absorption map** (spec §0.2):

  | babysit capability | coach v9 replacement |
  |--------------------|----------------------|
  | Token-count alerting | observer rule `06-token-threshold` |
  | Bash auto-approval | observer rule `13-bash-auto-approve` |
  | Aggregate approval | `atdd observer aggregate-approve` (spec §5.4) |
  | Naming drift correction | observer rule `14-canonical-naming-drift` |
  | Layout drift correction | observer rule `15-layout-drift` |
  | Violation detection | observer rules `04-out-of-scope-edit`, `16-smoke-skip` |
  | Dashboard (`_render_dashboard`) | `atdd observer status` (spec §5.4) |
  | Workspace-state polling | Replaced by event-driven `runtime_watcher` (no parity test by design) |
  | Phase-cache-via-labels | Replaced by coach state-machine phase ownership (no parity test by design) |

  Migration: run `atdd observer status` for the dashboard, `atdd observer
  aggregate-approve` for batch approval, or `atdd coach` for end-to-end
  orchestration per `atdd-coach-spec-v9.md §0.2` and `§5.4`.

- **`atdd orchestrate`** — decommissioned in coach v9 (spec §11.3, issue #531).
  Use `atdd coach <issue-numbers>` instead. Every flag maps directly per
  `atdd-coach-spec-v9.md §5.1`.
