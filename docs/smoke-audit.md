# SMOKE Test Audit

Classification of `# Phase: SMOKE` acceptance tests against real-infrastructure criteria.

| acceptance-URN | entry-point-coverage | assertion-target | handoff-coverage | incident-cross-ref |
|---|---|---|---|---|
| acc:mediate-worker-decisions:C004-SMOKE-001-live-dangerous-not-auto-answered | real (live cmux + claude worker, spy ClaudeCoach) | escalation recorded + loud-logged + no feed.reply + coach never consulted | worker → cmux Feed → feed_daemon → escalations.jsonl | #966; live blocked on #967 (worker prompts not yet published to the Feed) |
| acc:mediate-worker-decisions:E004-SMOKE-001-live-loop-answers-blocked-agent | real (live cmux + claude worker) | blocked decision answered via feed.*.reply | worker → cmux Feed → feed_daemon → feed.question.reply | #966; live blocked on #967 |
| acc:mediate-worker-decisions:E005-SMOKE-001-live-restart-no-double-answer | real (live cmux + claude worker) | restart re-hydrates answered-set, no double answer/escalation | daemon restart → verdicts.jsonl + escalations.jsonl re-hydration | #966; live blocked on #967 |
| acc:mediate-worker-decisions:D002-SMOKE-001-live-second-instance-refused | real (daemon subprocess + pidfile) | second daemon instance refused by PidfileLock | N/A (single component) | #966 (real process smoke, passes) |
| acc:mediate-worker-decisions:R002-SMOKE-001-live-sigterm-clean-shutdown | real (daemon subprocess) | SIGTERM exits the poll loop and releases the pidfile | N/A (single component) | #966 (real process smoke, passes) |
| acc:mediate-worker-decisions:E008-SMOKE-001-live-spawned-worker-decision-appears-blocked-in-feed | real (live cmux + claude worker via the production launch builders; no mocks) | a blocking decision appears as a pending item in cmux feed.list | spawn (claude-code adapter + _build_cmux_native_command, Bash-free) → worker decides → cmux wrapper hook → feed.list | #971 (live verified 2026-06-06; leash retired, evidence below) |
| acc:mediate-worker-decisions:C006-SMOKE-001-live-bash-decision-surfaces-not-auto-executed | real (live cmux + claude worker via the production launch builders; no mocks) | a Bash command surfaces as a pending kind=permissionRequest item (command in tool_input), not auto-executed | spawn → worker Bash → cmux wrapper hook → feed.list | #971 (live verified 2026-06-06; deny-pattern `rm` surfaces pending while safe `echo` auto-approves — evidence below) |
| acc:mediate-worker-decisions:Y002-SMOKE-001-live-worker-launch-argv-matches-policy | real (live toolkit-spawned claude worker via production builders) | captured launch argv has policy auto_allow in --allowedTools, Bash + bypass flag absent | spawn → DecisionSurfacingPolicy values → claude argv | #971 (live verified 2026-06-06; argv has `Read Edit Write TodoWrite Glob Grep WebFetch`, no Bash/bypass — evidence below) |
| acc:mediate-worker-decisions:L004-SMOKE-001-live-worker-has-active-feed-hook | real (live toolkit-spawned claude worker under cmux wrapper) | CMUX_SURFACE_ID set, live socket, PermissionRequest→cmux hooks feed active (proven by a real published item) | spawn → cmux wrapper → injected hook → feed.list | #971 (live verified 2026-06-06; worker's published permissionRequest confirms the hook path was live — evidence below) |
| acc:mediate-worker-decisions:L003-SMOKE-001-live-multi-question-located-whole | real (live cmux + claude worker) | a 3-question item located as a 3-block document, not flattened | worker → cmux Feed (questions[]) → feed_item_mapper → DecisionDocument | #976 (live; top-level cmux+claude publishes AskUserQuestion to the Feed, passes) |
| acc:mediate-worker-decisions:E006-SMOKE-001-live-decider-answers-whole-doc | real (live cmux + claude worker, real LlmCoach over claude -p) | verdict carries a non-empty answer for every block | DecisionDocument → LlmCoach (claude -p) → DecisionAnswer | #976 (live; real LLM decider, passes) |
| acc:mediate-worker-decisions:E007-SMOKE-001-live-multi-question-all-answered | real (live cmux + claude worker, real LlmCoach) | flat selections covering every question (checkbox incl.) resolves the item, worker proceeds | worker → cmux Feed → bridge → feed.question.reply (flat selections) | #976 (live headline; cmux feed.question.reply takes flat selections:[label], verified, passes) |
| acc:mediate-worker-decisions:E009-SMOKE-001-worker-actually-proceeds-after-reply | real (live cmux-native claude worker, real LlmCoach + CmuxWorkerAdvance) | worker's screen advances past the native menu (not merely Feed item resolved); screen-before parked / screen-after answered captured as evidence | worker → cmux Feed → bridge reply → WorkerAdvance verify → send-key fallback → re-verify | #986 (live headline; reproduces the cmux-native reply/menu race, asserts worker actually unblocked, evidence-bound per #983) |
| acc:mediate-worker-decisions:C005-SMOKE-001-live-mixed-document-not-auto-answered | real (harness verified real) | dangerous block in a mixed document escalates whole, never auto-answered | worker → cmux Feed → feed_daemon → escalations.jsonl | #976; not inducible live (cmux questions choice-only; dangerous permission doesn't block under auto-mode, like C003/C004) — hermetic C005 unit+integration carry the guarantee |
| acc:mediate-worker-decisions:L005-SMOKE-001-live-two-workers-no-cross-decide | real (two live cmux-native claude workers in two workspaces) | each workspace-scoped CmuxFeedSource returns only its own worker's decision; the two scoped result sets share no request_id (no cross-decide) | worker A / worker B → cmux Feed → per-workspace scoped CmuxFeedSource (surface.list identity) | #993 (live headline; reproduces the two-daemon cross-decide and proves the workspace scope isolates each consumer, evidence-bound per #983) |
| acc:mediate-worker-decisions:E010-SMOKE-001-live-start-launches-scoped-daemon | real (atdd coach start spawns the feed_daemon CLI as a managed subprocess; /tmp scratch runtime dir) | a per-workspace manager pidfile is written and names a live feed_daemon process scoped to the workspace | atdd coach start → gate → daemon_manager subprocess spawn (feed_daemon CLI, --workspace) → manager pidfile | #998 (live headline; managed-process launch, evidence-bound per #983; skips cleanly when cmux absent) |
| acc:mediate-worker-decisions:L007-SMOKE-001-live-worktree-worker-decision-not-swallowed | real (live cmux-native claude worker that cd's into a git worktree, blocked on a real AskUserQuestion) | a workspace-scoped CmuxFeedSource INCLUDES the worktree-launched worker's pending decision (the daemon would decide/escalate it) rather than scoping it out; the matched worktree cwd / workstream captured as evidence | worker → cd worktree → cmux Feed → per-workspace scoped CmuxFeedSource (surface.list launch cwd → git worktree set + no-empty-scope degrade) | #1004 (live headline; reproduces the #993 worktree regression where the scoped read swallowed a real worker's decision, proves the worktree-aware scope includes it, evidence-bound per #983; skips cleanly when cmux absent) |
| acc:mediate-worker-decisions:M003-SMOKE-001-live-daemon-writes-a-verdict | real (live cmux + claude worker; production-wired daemon via build_feed_daemon_from_repo with real CmuxFeedSource + LlmCoach over claude -p; /tmp scratch ledger dir) | the daemon completes a REAL decision and verdicts.jsonl gains a line (the daemon writes a verdict), not merely that the scoped source includes the item | worker → cmux Feed → feed_daemon tick → FeedRunnerUseCase → LlmCoach (claude -p) → JsonlVerdictLedger (verdicts.jsonl) | #1007 (live headline the L007 inclusion smoke missed: live verified 2026-06-08 — verdict_written=True, verdict_lines=1; reproduces the silent-decide failure; evidence-bound per #983; skips cleanly when cmux absent) |
| acc:mediate-worker-decisions:M004-SMOKE-001-real-spawn-captures-daemon-output-to-log | real (a real cmux surface launched via the production CmuxSurfaceDaemonLauncher running a marker-printing command; /tmp scratch daemon.log) | the on-disk daemon.log contains the surface command's printed marker — its stdout was captured to the durable log | CmuxSurfaceDaemonLauncher.spawn(argv, log_path) → cmux surface stdout (>> daemon.log 2>&1) → daemon.log | #1007 reopened (observability smoke; proves a runtime failure leaves a diagnosable trace even with the daemon inside a cmux surface; skips cleanly when cmux absent) |
| acc:mediate-worker-decisions:L006-SMOKE-001-live-wait-emits-induced-escalation | real (live managed daemon + induced escalation: worker_stuck or dangerous decision) | atdd coach wait prints exactly the induced escalation record as one JSON line then exits; a second wait does not re-emit it | worker → cmux Feed → feed_daemon → escalations.jsonl → atdd coach wait (cursor-tracked) → stdout | #998 (live headline; cursor-tracked notify pass closes the autonomous loop, evidence-bound per #983; skips cleanly when cmux absent) |
| acc:mediate-worker-decisions:M005-SMOKE-001-real-coach-start-managed-daemon-writes-a-verdict | real (live cmux + claude worker; the REAL `atdd coach start` cmux-surface daemon launch — NOT the loop directly, NOT feed_daemon_cli foreground, NOT a live-parent subprocess; the daemon is a cmux surface parented to cmux; /tmp scratch runtime root) | the MANAGED daemon's own verdicts.jsonl gains a line — the daemon launched as a cmux surface by the production command reached cmux cleanly and recorded a real decision | worker → `atdd coach start` (CoachRuntime.start) → CmuxSurfaceDaemonLauncher (cmux new-workspace --command) → feed_daemon → CmuxFeedSource (cmux rpc) → LlmCoach (claude -p) → JsonlVerdictLedger (verdicts.jsonl) | #1007 reopened (the headline gate prior rounds missed: M003-SMOKE drove the loop directly and passed while the real command orphaned its detached daemon — cmux rejects orphaned processes; live verified 2026-06-08 — daemon launched as cmux workspace, verdict_lines=1; skips cleanly when cmux absent) |
| acc:mediate-worker-decisions:C007-SMOKE-001-live-governance-question-not-auto-answered | real (live cmux + claude worker; real daemon tick via build_feed_daemon + real LlmCoach wrapped by a spy; no mocks) | a real "Approve → RED?" phase sign-off is escalated with cause=operator_reserved, NO feed reply, NO verdict, coach never consulted | worker → AskUserQuestion → cmux Feed → feed_daemon tick → governance gate (classify_governance) → escalations.jsonl | #1017 (governance headline; the direct counterpart of the wild auto-approval — a phase sign-off IS inducible as a normal blocking question, so this runs live; skips cleanly when cmux absent) |
| acc:mediate-worker-decisions:R003-SMOKE-001-live-stop-terminates-managed-daemon | real (atdd coach start spawns a real feed_daemon subprocess; atdd coach stop signals it; /tmp scratch dir) | the managed feed_daemon process exits on SIGTERM and its manager pidfile is removed | atdd coach start → daemon subprocess → atdd coach stop → SIGTERM → pidfile cleared | #998 (real process smoke; managed-daemon lifecycle, evidence-bound per #983; skips cleanly when cmux absent) |
| acc:mediate-worker-decisions:E011-SMOKE-001-live-decides-with-convention-loaded | real (live cmux + claude worker, real LlmCoach over claude -p; a thin recorder wraps the production claude provider CLI to capture the exact system context) | a verdict is produced AND the coach convention text was present in the decider's claude -p invocation | worker → cmux Feed → LlmCoach (claude -p --append-system-prompt coach-convention) → verdict | #987 (slice b live headline; live verified 2026-06-07 — verdict_produced=True, convention_present=True; decider decides AS A COACH, evidence-bound per #983; skips cleanly when cmux absent) |
| acc:mediate-worker-decisions:E014-SMOKE-001-live-answer-advances-parked-worker | real (live managed feed_daemon + cmux + claude worker; induced escalation parks the worker; operator runs the real atdd coach answer) | atdd coach answer delivers via the correct cmux feed verb and the parked worker's screen advances past the menu (screen-before parked / screen-after answered); the feed item reaches resolved with a decision | worker → cmux Feed → escalations.jsonl → atdd coach answer → feed_reply_mapper + CmuxFeedTransport (feed.*.reply) → worker advances | #1036 (Track A operational recovery headline; the direct reply path #1031 left missing for non-bootstrap escalations; evidence-bound per #983; live verified 2026-06-10 (worker advanced past menu, item resolved); skips cleanly when cmux absent) |
| acc:mediate-worker-decisions:C009-SMOKE-001-live-wrong-label-rejected-no-feed-reply | real (live cmux + claude worker parked on a real AskUserQuestion) | atdd coach answer with a non-exact label exits loudly naming invalid input + valid options, sends NO feed reply (no false delivered:true), worker stays parked | worker → cmux Feed → atdd coach answer label resolver (CmuxFeedSource.list_pending for valid labels) → reject before feed.question.reply | #1036 (reproduces the exact footgun from this session: cmux returns delivered:true silently on a label mismatch; evidence-bound per #983; live verified 2026-06-10 (wrong label rejected loudly, no reply, worker stayed parked); skips cleanly when cmux absent) |
| acc:mediate-worker-decisions:L008-SMOKE-001-live-status-surfaces-then-omits-after-answer | real (live managed feed_daemon that escalated a live worker's decision into escalations.jsonl) | atdd coach status lists the unanswered request_id with prompt/options before answering, and omits it after atdd coach answer resolves it | worker → cmux Feed → feed_daemon → coach-runtime/<ws>/escalations.jsonl → atdd coach status (unanswered surfacing read) | #1036 (closes the surfacing gap: an escalated decision had no reply path AND no surfacing, so the operator was never told; evidence-bound per #983; live verified 2026-06-10 (real daemon escalation surfaced, omitted after answer); skips cleanly when cmux absent) |
| acc:observe-and-correct:E008-SMOKE-001-delivery-waits-for-tui | synthetic (Python slow-start subprocess) | TUI ready-marker gate timing | single direction | #862; flagged for retrofit per #855 (synthetic-fixture-bypass + timing-flaky risk) |
| acc:observe-and-correct:E007-SMOKE-001-sentinel-enables-tui-submission | synthetic (Python echo-on-enter subprocess in raw termios) | submit sentinel (CR) delivery | single direction | #862; flagged for retrofit per #855 (synthetic-fixture-bypass) |
| acc:observe-and-correct:E003-SMOKE-001 | atdd-shim CLI subprocess | output.log contains CORRECTION_RECEIVED | dispatcher.dispatch → cli-return.jsonl → shim → agent stdin | #862 (rewritten from PersonaShim direct) |
| acc:observe-and-correct:E003-SMOKE-002 | atdd-shim CLI subprocess (`python -m atdd.coach.shim`) | captured stdout contains STDOUT_SENTINEL_E003_SMOKE_002 | shim pty → sys.stdout.buffer → operator-visible terminal | #843 (stdout forwarding) |
| acc:observe-and-correct:E004-SMOKE-001 | atdd spawn / cmd_spawn | shim is surface foreground process (ppid check), output.log grows | cmd_spawn → PersonaShim (via atdd-shim) → agent pty | #841 (spawn dispatch wiring) |
| acc:govern-lifecycle:E036-SMOKE-001-installed-shim-blocks-and-forwards-in-real-worktree | real (on-disk .atdd/bin/git installed in a real `git init` repo, real system git downstream, real shell PATH resolution) | block exits 1 + shared core.bare not poisoned; real `git status` forwards exit 0 | shell PATH → .atdd/bin/git shim → real git binary | #884 (agent-agnostic git-config bare guard; real binary, no synthetic stub) |
| acc:govern-lifecycle:C002-SMOKE-001-plan-tree-has-no-non-canonical-theme | real (validator scans the toolkit's own plan/ tree under REPO_ROOT) | zero non-canonical wagon themes reported (commons/plan/test/code/coach only) | plan/*/_*.yaml theme: declarations → check_must_be_canonical | #970 (canonical theme taxonomy; plan-time validator, no synthetic fixture) |
| acc:govern-lifecycle:C003-SMOKE-001-plan-tree-respects-boundary | real (validator scans the toolkit's own plan/ + src/ trees under REPO_ROOT) | zero unsuppressed commons-wagon-imports-coach violations (mediate-worker-decisions carve-out deferred to #951) | commons wagon src import scan → check_commons_coach_boundary | #970 (commons/coach boundary; plan-time validator, no synthetic fixture) |
| acc:govern-lifecycle:C004-SMOKE-001-plan-tree-urn-prefixes-align | real (validator scans the toolkit's own plan/ tree under REPO_ROOT) | zero unsuppressed produced-URN theme-prefix mismatches (commons:decision:* carve-out deferred to #951) | wagon produce[].name theme-prefix vs theme: → check_urn_namespace_matches | #970 (URN-namespace alignment; plan-time validator, no synthetic fixture) |
| acc:govern-lifecycle:C005-SMOKE-001-plan-tree-archetype-themes-align | real (validator scans the toolkit's own plan/ + src/ trees under REPO_ROOT) | zero plan/test/code wagons living outside their planner/tester/coder archetype root | wagon theme: vs archetype source root → check_archetype_alignment | #970 (archetype alignment; plan-time validator, no synthetic fixture) |
| acc:govern-lifecycle:C006-SMOKE-001-repo-config-keeps-commons-floor | real (validator resolves the toolkit's own .atdd/config.yaml under REPO_ROOT) | zero theme-zero-mandatory violations; resolved set pins commons at digit 0 | .atdd/config.yaml themes: block → resolve_theme_set → check_theme_zero_mandatory | #970 (commons mandatory floor; plan-time validator, no synthetic fixture) |
| acc:govern-lifecycle:E014-SMOKE-002-runtime-shim-entry-refuses-forbidden-flag | real (`python -m atdd.runtime.agent_control` module CLI as a subprocess; no mocks/FakeMultiplexer/stub) | non-zero exit + stderr names `--dangerously-skip-permissions` + no agents/<id> dir created (no process launched) | N/A (single component — the launch boundary refuses before any handoff) | #969 (retire forbidden flag + close E014 guard gap in cli-return transport; real subprocess, operator-observable refusal) |
| acc:govern-lifecycle:E043-SMOKE-001-live-cmux-native-launch-feed-no-shim | real (live cmux 0.64.10 + claude worker via the production launch builders; no mocks/stub) | worker boots with NO `atdd.coach.shim`/PersonaShim in path; positional prompt auto-submits (feed `userPrompt`+`stop`); activity publishes to `feed.list` with `source=claude` | build_agent_seed_argv + build_cmux_launch_argv → `cmux new-workspace --command` → claude positional seed → cmux wrapper hooks → `cmux rpc feed.list` | #978 (live verified 2026-06-05; no shim, no synthetic fixture — evidence below) |
| acc:consolidate-coach-workspace:C001-SMOKE-001-live-never-collapse | real (N>=2 live cmux-native per-workspace claude workers; no mocks) | after the layout pass, `surface.list` per worker-workspace yields exactly one worker identity — no worker migrated into another worker's or the coach's workspace (no daemon-scope collapse) | per-workspace workers → conformance pass (geometry over per-workspace surfaces) → cmux rpc surface.list per workspace | #865 (headline never-collapse safety; reproduces the #1013 _resolve_scope union hazard at N-worker scale; skips cleanly when cmux absent) |
| acc:consolidate-coach-workspace:E003-SMOKE-001-meta-smoke-print-theater-guard | real (live conformance pass driven through a recording multiplexer fake that captures every backend call) | a backend layout primitive invocation is observed; a layout-target print with zero layout primitive calls FAILS the smoke (catches print-theater regressions) | apply_canonical_name_and_layout shim → apply-layout use case → MultiplexerLayoutPort (recording) → recorded call log | #865 (meta-smoke guarding the core log-theater bug; asserts the real invocation, not the print) |
| acc:consolidate-coach-workspace:E004-SMOKE-001-validator-over-live-surface-names | real (the bound naming validator evaluated over a real cmux `surface.list`) | a role-aware managed surface name passes; a name lacking the role segment is flagged for re-application | cmux rpc surface.list → surface_state events → bound canonical-role-name validator | #865 (naming half of the stop-the-log-theater enforcement; skips cleanly when cmux absent) |
| acc:drive-state-machine:E002-SMOKE-001-rerun-after-no-marker-spawn-reattempts-current | real (a real issue warm-resumed at RED in a /tmp runtime dir; the RED persona's spawn rigged to fail before writing done.json so no current-phase completion marker is recorded; atdd coach <N> re-run) | the re-run re-spawns the RED persona (tester), NOT a GREEN coder; the atdd:RED label is unchanged; no earlier-persona agent_done replay advances the phase | atdd coach <N> → warm-resume completion-gate (current-phase done.json marker) → re-spawn-current vs advance-next | #1055 (the live #1051 RED-skip defect: a transient cmux Broken-pipe RED-spawn failure left RED with no done.json, and warm-resume + the unguarded agent_done branch kept advancing RED→GREEN on every re-run; skips cleanly when coach runtime absent) |

## E043-SMOKE-001 live evidence (2026-06-05)

Captured by running the smoke against real cmux 0.64.10 + claude inside a cmux
session (`PYTHONPATH=src <venv> -m pytest -s
src/atdd/coach/commands/tests/test_e043_smoke_001_live_cmux_native_launch.py`):

```
workspace_ref : workspace:84
worker_cwd    : /private/var/folders/.../atdd-e043-smoke-42345
launch_argv   : ['cmux', 'new-workspace', '--name', 'atdd-e043-smoke-42345',
                 '--cwd', '.../atdd-e043-smoke-42345', '--command',
                 "claude 'Reply with exactly this token and nothing else: SMOKE-OK-978. Do not use any tools.' --permission-mode acceptEdits --allowedTools Read"]
feed_kinds    : ['sessionStart', 'stop', 'userPrompt']
turn_item     : {"kind": "stop", "source": "claude", "status": "telemetry",
                 "cwd": ".../atdd-e043-smoke-42345",
                 "id": "75329F80-03B9-4BAB-B18C-4C278737419C",
                 "workstream_id": "claude-ac70674f-0e3e-4b16-8465-28e452d3727c",
                 "created_at": "2026-06-05T20:34:38Z"}
shim_in_path  : []   (expected: [])
```

Proves all three acceptance criteria jointly: (1) `cmux new-workspace --command`
booted a claude worker with **no shim** in the launch path (`shim_in_path: []`,
and the `--command` string is a bare `claude` invocation); (2) the **positional
prompt auto-submitted** — the Feed recorded a `userPrompt` and a `stop` (the
worker took and finished its first turn unattended, no paste/sentinel); (3) the
worker's activity **published to `feed.list` with `source=claude`**, i.e. the
cmux wrapper's Feed hooks fired **without** the shim. `sessionStart` alone is
explicitly rejected by the smoke (would prove only boot, not auto-submit), so the
green is not a #855-style fake.

## #971 producer live evidence (E008 / C006 / Y002 / L004-SMOKE-001, 2026-06-06)

The headline proof that retiring the leash makes a spawned worker's ungated
tool use surface to the Feed. Captured against real cmux + claude inside a cmux
session via the production launch builders (the `claude-code` adapter — now
Bash-free — composed with `spawn._build_cmux_native_command`), e.g.
`ATDD_LIVE_SMOKE=1 PYTHONPATH=src <venv> -m pytest -s
src/atdd/mediate_worker_decisions/surface_worker_decisions/tests/test_c006_smoke_001_live_bash_decision_surfaces_not_auto_executed.py`
(`1 passed in 12.36s`).

Launch command (Y002 — argv is the exact image of the policy, **Bash absent**):

```
claude 'Use the Bash tool to run exactly this command and nothing else: rm -rf /private/tmp/SMOKE971-...-does-not-exist' \
       --permission-mode acceptEdits \
       --allowedTools 'Read Edit Write TodoWrite Glob Grep WebFetch'
```

The worker's Bash command surfaced as a **pending `permissionRequest`** in
`cmux rpc feed.list` (C006 / E008), instead of auto-executing:

```json
{
  "kind": "permissionRequest",
  "status": "pending",
  "source": "claude",
  "tool_name": "Bash",
  "tool_input": "{\"command\":\"rm -rf /private/tmp/SMOKE971-b21be92a-does-not-exist\",\"description\":\"Remove nonexistent temp path\"}",
  "request_id": "claude-...-PermissionRequest-Bash-1780740994225",
  "cwd": "/private/tmp/smoke971-960b96",
  "workstream_id": "claude-ffad241a-...",
  "created_at": "2026-06-06T10:16:34Z"
}
```

Contrast that proves the gate is real (not a #855 fake): a **safe** `echo`
command run the same way published only `toolUse`/`status=telemetry` (Claude
auto-approves it) and the worker ran to `stop` — whereas the **deny-pattern**
`rm` blocked as a `pending` `permissionRequest`. The producer guarantees the
decision reaches the Feed; the daemon's `tool_input_safety`/`match_danger` (C003
/ C004) decides auto vs human_required. The published item also proves the
Feed-publishing hook path was live for the worker (L004): `source=claude` +
`request_id` exist only because the cmux wrapper's `PermissionRequest -> cmux
hooks feed` hook fired. The workspace is closed after capture (no orphan panes).

## Histogram

Breakdown of SMOKE acceptance rows by structural-bypass cause.

| cause | count |
|---|---|
| entry-point-coverage (synthetic stub, not real CLI) | 1 (E003-SMOKE-001 — retrofitted in #862) |
| synthetic-fixture (FakeMultiplexer / _SYNTHETIC_AGENT) | 0 (suppressed or retrofitted) |
| producer-only assertion (no consumer-side check) | 0 |
| handoff-gap (producer→consumer not in one test) | 0 |

## Future Tracking

Post-SMOKE regression metric — tracks bugs discovered after SMOKE passed CI.

| release-wave | post-SMOKE-bugs | expectation |
|---|---|---|
| v3.83.x | 2 (startup race #862, no-submit #862) | 0 |
| v3.84.x | TBD | 0 |
# SMOKE Acceptance Audit

**Created:** 2026-05-25
**Issue:** #855 — Investigate Smoke Test Systemic False Greens
**WMBT:** `wmbt:govern-lifecycle:E027`

Four production bugs shipped through green-SMOKE in the 2026-05-21 → 2026-05-24 session.
Each SMOKE test was technically passing — the assertion it made was true under the fixture
conditions it set up. Those conditions were not representative of production. This document
classifies every `phase: SMOKE` acceptance by structural cause and records the histogram
of bypass patterns.

---

## Classification Table

| acceptance-URN | entry-point-coverage | assertion-target | handoff-coverage | incident-cross-ref |
|---|---|---|---|---|
| acc:observe-and-correct:E006-SMOKE-001-stdin-bytes-reach-wrapped-subprocess | synthetic (cat subprocess) | stdin bytes round-trip | single direction | #861; flagged for retrofit per #855 (synthetic-fixture-bypass) |
| acc:consolidate-coach-workspace:D001-SMOKE-001-real-layout-holds-as-workers-added | real (atdd spawn + cmux) | layout persistence | N/A (UI state) | — |
| acc:consolidate-coach-workspace:E001-SMOKE-001-real-coach-tab-shows-every-issue | real (atdd spawn) | cmux pane list | N/A (UI state) | — |
| acc:consolidate-coach-workspace:E002-SMOKE-001-real-spawn-yields-one-tab-no-obs | real (atdd spawn) | pane count | N/A (UI state) | — |
| acc:consolidate-coach-workspace:Y001-SMOKE-001-real-multiplexer-shows-one-coach-tab | real (atdd spawn + cmux) | coach-tab presence | N/A (UI state) | — |
| acc:consolidate-coach-workspace:Y002-SMOKE-001-real-spawn-yields-one-tab | real (atdd spawn) | pane count | N/A (UI state) | — |
| acc:dispatch-ux-defaults-and-primer:E001-SMOKE-001-pane-mode-in-real-cmux-session | real (atdd spawn + cmux) | pane mode selection | N/A (single component) | — |
| acc:dispatch-ux-defaults-and-primer:E002-SMOKE-001-no-prompt-auto-in-piped-invocation | real (atdd spawn piped) | prompt suppression | N/A (single component) | — |
| acc:dispatch-ux-defaults-and-primer:E003-SMOKE-001-coach-invoked-from-worktree-parent | real (atdd coach) | invocation path | N/A (single component) | — |
| acc:dispatch-ux-defaults-and-primer:E004-SMOKE-001-worktree-reused-not-duplicated | real (atdd coach) | worktree reuse | N/A (single component) | — |
| acc:dispatch-ux-defaults-and-primer:E005-SMOKE-001-primer-printed-in-real-cmux-session | real (atdd coach + cmux) | primer output | N/A (single component) | — |
| acc:dispatch-ux-defaults-and-primer:E006-SMOKE-001-no-orphan-pane-after-spawn-failure | real (atdd spawn) | pane cleanup | N/A (single component) | — |
| acc:dispatch-ux-defaults-and-primer:E007-SMOKE-001-new-surface-in-pane-no-broken-pipe | real (atdd spawn) | pipe handling | N/A (single component) | — |
| acc:dispatch-ux-defaults-and-primer:Y001-SMOKE-001-help-text-shows-timeout-in-real-shell | real (atdd CLI) | help text content | N/A (single component) | — |
| acc:dispatch-ux-defaults-and-primer:Y002-SMOKE-001-banner-absent-after-sync-in-real-env | real (atdd sync) | banner suppression | N/A (single component) | — |
| acc:dispatch-ux-defaults-and-primer:Y003-SMOKE-001-resume-absent-from-real-help-output | real (atdd CLI) | help text content | N/A (single component) | — |
| acc:dispatch-ux-defaults-and-primer:Y004-SMOKE-001-real-template-render-excludes-sibling-deps-from-merge-wait | real (atdd session-template) | rendered output | N/A (single component) | — |
| acc:dispatch-ux-defaults-and-primer:Y004-UNIT-007-planner-validator-flags-bare-deps | real (atdd validate planner) | violation detection | N/A (validator) | — |
| acc:govern-lifecycle:D018-SMOKE-001-jel-app-repro-and-allowlist-round-trip | real (atdd CLI) | allowlist round-trip | both ends (write + read) | — |
| acc:govern-lifecycle:E003-SMOKE-001-real-validator-suite-includes-this-validator | real (atdd validate) | validator discovery | N/A (meta-validator) | — |
| acc:govern-lifecycle:E003-SMOKE-002-rules-grep-finds-both-new-rules | real (atdd rules grep) | rule discovery | N/A (meta-validator) | — |
| acc:govern-lifecycle:E003-SMOKE-003-rules-show-resolves-each-rule | real (atdd rules show) | rule resolution | N/A (meta-validator) | — |
| acc:govern-lifecycle:E004-SMOKE-001-rule-blocks-empty-graph-context | real (atdd validate coach) | rule enforcement | N/A (meta-validator) | — |
| acc:govern-lifecycle:E005-SMOKE-001-real-validate-coach-runs-extended-drift-validator | real (atdd validate coach) | validator execution | N/A (meta-validator) | — |
| acc:govern-lifecycle:E006-SMOKE-001-real-tester-suite-runs-both-validators | real (atdd validate tester) | validator discovery | N/A (meta-validator) | — |
| acc:govern-lifecycle:E006-SMOKE-002-rules-resolve-against-real-registry | real (atdd rules) | rule resolution | N/A (meta-validator) | — |
| acc:govern-lifecycle:E008-SMOKE-001-registration-visible-cross-worktree | real (atdd manifest) | cross-worktree visibility | both ends (write + read) | — |
| acc:govern-lifecycle:E009-SMOKE-001-real-validate-coach-runs-runtime-guard | real (atdd validate coach) | runtime guard | N/A (meta-validator) | — |
| acc:govern-lifecycle:E010-SMOKE-001-real-branch-creation-starts-at-origin | real (atdd branch) | branch origin | N/A (single component) | — |
| acc:govern-lifecycle:E011-SMOKE-001-real-fs-lock-prevents-concurrent-coaches | real (atdd coach) | fs lock enforcement | N/A (single component) | — |
| acc:govern-lifecycle:E012-SMOKE-001-pre-commit-hook-installed-allows-manifest-only | real (git commit) | hook behavior | N/A (single component) | — |
| acc:govern-lifecycle:E012-SMOKE-002-issue-reconcile-wired-in-cli | real (atdd issue reconcile) | CLI wiring | N/A (single component) | — |
| acc:govern-lifecycle:E013-SMOKE-001-live-gh-search-runs-without-error | real (gh search) | exit code | N/A (single component) | — |
| acc:govern-lifecycle:E014-SMOKE-001-spawn-guard-reachable-from-cli | real (atdd spawn) | guard reachability | N/A (single component) | — |
| acc:govern-lifecycle:E015-SMOKE-001-gate-output-contains-rules-in-live-repo | real (atdd gate) | output content | N/A (single component) | — |
| acc:govern-lifecycle:E016-SMOKE-001-backfill-on-real-fixture-suppresses-violations | real (atdd suppress backfill) | suppression effect | N/A (single component) | — |
| acc:govern-lifecycle:E017-SMOKE-001-docs-models-md-has-valid-structure | real (docs/MODELS.md) | file structure | N/A (single component) | — |
| acc:govern-lifecycle:E017-SMOKE-002-atdd-manifest-backfill-cli-wired | real (atdd manifest backfill) | CLI wiring | N/A (single component) | — |
| acc:govern-lifecycle:E018-INTEGRATION-001-scope-flag-in-cli-help | real (atdd validate --help) | help text | N/A (single component) | — |
| acc:govern-lifecycle:E018-INTEGRATION-002-scope-changed-files-exits-zero-on-clean-branch | real (atdd validate --scope changed-files) | exit code | N/A (single component) | — |
| acc:govern-lifecycle:E018-SMOKE-001-scoped-check-exits-zero-on-this-branch | real (atdd validate --scope changed-files) | exit code | N/A (single component) | — |
| acc:govern-lifecycle:E019-INTEGRATION-001-published-issue-passes-body-validators | real (atdd validate coach) | body validation | N/A (single component) | — |
| acc:govern-lifecycle:E019-SMOKE-001-live-create-zero-edit-calls | real (atdd issue) | gh API calls | N/A (single component) | — |
| acc:govern-lifecycle:E020-SMOKE-001-live-sync-codex-produces-conductor-md | real (atdd sync codex) | file output | N/A (single component) | — |
| acc:govern-lifecycle:E021-INTEGRATION-001-ci-check-fails-on-drifted-pr | real (CI check) | check result | N/A (single component) | — |
| acc:govern-lifecycle:E021-SMOKE-001-registry-check-passes-on-main-after-chore-pr | real (atdd validate) | exit code on main | N/A (single component) | — |
| acc:govern-lifecycle:E022-SMOKE-001-post-commit-leaves-core-bare-unchanged | real (git commit) | core.bare value | N/A (single component) | — |
| acc:govern-lifecycle:E023-SMOKE-001-routine-push-requires-zero-gate-bypasses | real (git push) | bypass count | N/A (single component) | — |
| acc:govern-lifecycle:E024-SMOKE-001-merge-produces-exactly-one-publish-success | real (gh merge) | publish event count | both ends (merge → publish) | — |
| acc:govern-lifecycle:E025-INTEGRATION-001-consumer-repo-sweep-excludes-custom-themes-tests | real (atdd validate tester) | scope exclusion | N/A (single component) | — |
| acc:govern-lifecycle:E025-SMOKE-001-consumer-validator-rejects-toolkit-only-tests | real (atdd validate tester) | violation detection | N/A (single component) | — |
| acc:govern-lifecycle:E026-SMOKE-001-routine-push-zero-bypasses-after-retirement | real (git push) | bypass count | N/A (single component) | — |
| acc:govern-lifecycle:E027-SMOKE-001-audit-covers-all-current-smoke-acceptances | real (plan/ YAML scan) | audit coverage | N/A (meta-validator) | #855 |
| acc:govern-lifecycle:E028-SMOKE-001-validate-planner-clean-after-retrofit | real (atdd validate planner CLI) | exit code 0 | N/A (meta-validator) | #855 |
| acc:govern-lifecycle:E029-SMOKE-001-retrofitted-smokes-pass-in-ci-without-bypasses | real (CI run, no bypass flags) | test suite result | both ends (post-retrofit) | #855 |
| acc:govern-lifecycle:E030-SMOKE-001-grep-returns-zero-matches | real (grep CLI on hook template files) | zero ATDD_SKIP_* matches | N/A (single component) | — |
| acc:govern-lifecycle:E031-SMOKE-001-emergency-cli-wired-in-atdd | real (python3 -m atdd.cli emergency) | EMERGENCY_BYPASS + audit-jsonl creation | N/A (single component) | — |
| acc:govern-lifecycle:E032-SMOKE-001-installed-shim-blocks-in-real-worktree | real (atdd init + gh issue create) | shim blocks command in live worktree | N/A (single component) | #816 |
| acc:govern-lifecycle:E033-SMOKE-001-real-commit-rejects-staged-create | real (git commit with pre-commit hook) | pre-commit rejects staged gh issue create | N/A (single component) | #816 |
| acc:govern-lifecycle:E034-SMOKE-001-real-init-installs-and-warns | real (atdd init) | init installs shim + envrc entry | N/A (single component) | #816 |
| acc:govern-lifecycle:E035-SMOKE-001-real-import-purity-and-yaml-load | real (child interpreter subprocess imports atdd.coach.core + on-disk YAML load) | fresh import leaks no subprocess; phase_machine.convention.yaml parses to 9 phases | N/A (single component) | #888 |
| acc:govern-lifecycle:E037-SMOKE-001-real-collect-reports-emission | real (child interpreter subprocess runs the disposition-gate emit adapter writing an on-disk JSONL sink) | emitted ValidatorReport row carries the violation rule_id with disposition=block | N/A (single component) | #890 |
| acc:govern-lifecycle:E038-SMOKE-001-real-worktree-core-bare-false-on-disk | real (atdd.runtime.worktree.ensure_issue_worktree against a real on-disk git repo + real git CLI) | new worktree's per-worktree core.bare override reads false (I-9 canonical fix); shared config not left bare | N/A (single component) | #892 |
| acc:govern-lifecycle:E040-SMOKE-001-real-fs-run-roundtrip | real (two independently-constructed JsonlPersistenceStore instances over a real on-disk temp repo; real events.jsonl/decisions.jsonl/conventions.snapshot.yaml on disk) | a second store instance replays the identical on-disk event stream and load_run reconstructs an equal RunState — durability across instance boundaries | JsonlPersistenceStore(writer) → .atdd/runtime/runs/<id>/*.jsonl → JsonlPersistenceStore(reader) replay_events + load_run | #894 |
| acc:govern-lifecycle:E041-SMOKE-001-coach-end-to-end-via-trainrunner | real (coach.run cold-start against a real on-disk temp ATDD repo; real .atdd/runtime/runs/<id>/ scaffold + RunStarted event written to disk) | the per-issue drive is reached through JsonlTrainRunner.start_issue and a real run dir lands on disk; a repo grep finds no coach.commands.coach._drive_* private call outside the deprecated shim; runner_iface/issue_runner stay within §3.3 | coach.run → JsonlTrainRunner.start_issue → JsonlPersistenceStore.create_run (.atdd/runtime/runs/<id>/) → issue_runner.drive_single_issue | #895 |
| acc:govern-lifecycle:E042-SMOKE-001-jsonl-crash-recovery-identical-decisions | real (a real on-disk durable run is driven several phases in via the single-writer events.jsonl + frozen conventions.snapshot.yaml; a brand-new JsonlTrainRunner instance — the post-crash process with no in-memory state — replays it from disk via resume; GitHub evidence is a hermetic double so materialize_evidence is a pure function of the manifest + frozen snapshot) | the decision resume records equals the live loop's next coach.core.next_transition decision, and re-resuming on another fresh instance is identical (deterministic across process restart); resume writes no new PhaseAdvanced (no double-execution) — the §10.3 gate that governs any future Temporal adoption (§16 R-7) | kill -9 (discard runner) → JsonlTrainRunner(fresh).resume → load_conventions_for_run(frozen snapshot) + replay_events → materialize_evidence → coach.core.next_transition → RunResumed + decisions.jsonl | #896 |
| acc:govern-lifecycle:E044-SMOKE-001-toolkit-registry-build-leaves-no-stray-stub-dirs | real (the committed `.atdd/config.yaml` artifact run through the production `RegistryBuilder.build_all(mode="apply")`; no mocks/fakes) | the toolkit's shipped config declares only `code.toolkit: src/atdd`, and a real build leaves no `python/`/`supabase/`/`telemetry/` stub dirs | committed `.atdd/config.yaml` → RegistryBuilder.build_all → on-disk registry dirs | #984 (sibling of #970; reads the real shipped config, drives the real build) |
| acc:govern-lifecycle:L002-SMOKE-001-meta-walker-zero-hits-on-post-retrofit-repo | real (walk_all_smoke_acceptances_for_anti_patterns) | anti-pattern hits list | N/A (meta-validator) | #855 |
| acc:govern-lifecycle:R004-SMOKE-001-real-linked-worktree-recognized-worktree-ready | real (git worktree) | worktree detection | N/A (single component) | — |
| acc:govern-lifecycle:Y004-SMOKE-001-pre-commit-template-has-drift-notice | real (template file) | file content | N/A (single component) | — |
| acc:govern-lifecycle:Y005-SMOKE-001-reconcile-wired-in-cli | real (atdd issue reconcile) | CLI wiring | N/A (single component) | — |
| acc:govern-lifecycle:E045-SMOKE-001-real-subprocess-check-blocks-through-live-registry | real (real CommandGateCheck shells out to a real subprocess; live GateRegistry + evaluate_transition_gate; no mocks) | a genuinely-failing subprocess yields proceed=False (blocks), a genuinely-passing one yields proceed=True | CommandGateCheck → GateRegistry → evaluate_transition_gate → OS subprocess | #1020 (the enforcing-gate keystone; production wiring of the gate decision against a real process) |
| acc:govern-lifecycle:E050-SMOKE-001-real-cli-blocked-without-token-proceeds-after-coach-approve | real (real register_approval_checks → real ApprovalTokenGateCheck → real evaluate_transition_gate; the real `atdd coach approve` command writes a real signed token file under a real worktree; no mocks) | no token ⇒ proceed=False (gate blocks); after the real approve command writes the token ⇒ proceed=True; a PLANNED→RED token does not unlock RED→GREEN | register_approval_checks → GateRegistry → evaluate_transition_gate → ApprovalTokenGateCheck → filesystem token (Feed-decoupled) | #1017 (operator-approval enforcement; production wiring of the gate decision against the real token file the operator command produces) |
| acc:govern-lifecycle:E046-SMOKE-001-real-missing-tool-fails-closed | real (real CommandGateCheck names a binary absent from the host PATH; the OS raises FileNotFoundError) | a real missing tool is converted to a FAIL → proceed=False (fail-closed) | CommandGateCheck → GateRegistry → evaluate_transition_gate → OS exec attempt | #1020 (fail-closed guarantee verified against the real OS, not a stubbed exception) |
| acc:govern-lifecycle:E047-SMOKE-001-real-toolkit-scan-discovers-and-resolves | real (production config-driven composition analysis over the live src/atdd tree; toolkit's own shipped .atdd/config.yaml; no mocks/fixtures) | the #865 four-tier feature is analyzed and its composition-root-wired files carry no false unwired violation (atdd. edges resolved against the src import root) | .atdd/config.yaml code.toolkit → resolve_scan_roots → analyze_python_root (real src/atdd scan) | #958 (config-driving holds end-to-end; the #955 false-violation regression is fixed against the real tree) |
| acc:govern-lifecycle:E048-SMOKE-001-real-toolkit-files-discovered-over-live-tree | real (production boundaries finder over the live src/atdd tree; toolkit's own shipped .atdd/config.yaml; no mocks/fixtures) | a known real toolkit implementation file is discovered and the negative fixtures are excluded | .atdd/config.yaml code.toolkit → resolve_scan_roots → find_implementation_files (real src/atdd scan) | #958 (boundaries finder honors code.toolkit against the real tree) |
| acc:govern-lifecycle:E049-SMOKE-001-new-violation-beyond-baseline-fails-the-gate | real (collect_toolkit_violations runs the production config-driven composition analysis over the real src/atdd tree; real grandfathered baseline resolved from .atdd/baselines/) | a new violation absent from the baseline leaks (fails the gate) while pre-existing grandfathered debt stays absorbed | .atdd/config.yaml code.toolkit → resolve_scan_roots → analyze_python_root (real src/atdd scan) → new_violations vs .atdd/baselines/four_tier_toolkit.yaml | #958 (the four-tier ratchet bites on growth, not on legacy; real scan, no mocks) |
| acc:implement-code:D003-UNIT-002-no-false-positives | real (atdd validate) | no false violations | N/A (validator) | — |
| acc:integrate-end-to-end:E001-SMOKE-001-cycle-reaches-complete | real (full ATDD cycle) | issue status | both ends (INIT → COMPLETE) | — |
| acc:integrate-end-to-end:E001-SMOKE-002-artifacts-readable | real (full ATDD cycle) | artifact readability | both ends (write + read) | — |
| acc:integrate-end-to-end:M001-SMOKE-001-integration-log-covers-every-handoff | real (full ATDD cycle) | log completeness | both ends (all handoffs) | — |
| acc:integration-hardening:C002-SMOKE-001-pre-push-fires-on-real-git-push | real (git push) | hook execution | N/A (single component) | — |
| acc:integration-hardening:C002-SMOKE-002-commit-msg-fires-on-real-git-commit | real (git commit) | hook execution | N/A (single component) | — |
| acc:integration-hardening:C003-SMOKE-001-prepush-validator-fires-via-git-push | real (git push) | validator execution | N/A (single component) | — |
| acc:integration-hardening:C004-SMOKE-001-validator-via-real-gh-pr-list-against-repo | real (gh pr list) | validator execution | N/A (single component) | — |
| acc:integration-hardening:C005-SMOKE-001-coach-run-no-premature-advance-on-seeded-stale-done | real (atdd coach run) | state transition | N/A (single component) | — |
| acc:integration-hardening:E001-SMOKE-001-watcher-real-infrastructure | real (atdd coach watcher) | event delivery | both ends (emit + receive) | — |
| acc:integration-hardening:E006-SMOKE-001-hook-blocks-real-claude-invocation-against-installed-classifier | real (claude invocation) | hook block | N/A (single component) | — |
| acc:integration-hardening:E007-SMOKE-001-wave-plan-against-real-repo-graph | real (atdd coach wave planning — commands/wave_planning.py) | wave plan output | N/A (single component) | — |
| acc:integration-hardening:E008-SMOKE-001-nonexistent-pr-exits-0-with-broken-verdict | real (atdd review) | exit code | N/A (single component) | — |
| acc:integration-hardening:E009-SMOKE-001-resume-real-orchestration | real (atdd coach resume) | orchestration resume | N/A (single component) | — |
| acc:integration-hardening:M002-SMOKE-001-prepush-hook-fires-on-real-git-push | real (git push) | hook execution | N/A (single component) | — |
| acc:integration-hardening:Y001-SMOKE-001-handlers-importable-and-decisions-written-on-real-fs | real (fs write) | decisions persistence | both ends (write + read) | — |
| acc:integration-hardening:Y003-SMOKE-001-guard-catches-real-live-repo-contamination | real (atdd validate) | contamination detection | N/A (validator) | — |
| acc:integration-hardening:Y004-SMOKE-001-pre-push-hook-with-outdated-version-exits-1-cleanly | real (git push) | hook exit code | N/A (single component) | — |
| acc:integration-hardening:Y005-SMOKE-001-pipx-install-detection-end-to-end | real (atdd upgrade) | install detection | N/A (single component) | — |
| acc:integration-hardening:Y006-SMOKE-001-init-force-in-linked-worktree-writes-config-worktree-file | real (atdd init) | config file location | N/A (single component) | — |
| acc:judge-ambiguous-decisions:D006-SMOKE-001-review-returns-parseable-verdict | real (atdd review) | verdict JSON | N/A (single component) | — |
| acc:observe-and-correct:E003-SMOKE-001-correction-loop-end-to-end | synthetic→real (retrofitted #855) | correction delivery via stdin | both ends (observer writes + shim delivers) | #824, #841, #854 |
| acc:observe-and-correct:E003-SMOKE-002-operator-stdout-visible | synthetic→real (retrofitted #855) | proc.stdout bytes | N/A (single component) | #843 |
| acc:observe-and-correct:E004-SMOKE-001-real-spawn-uses-shim-process-tree | real (atdd spawn via _ProcessLaunchingFakeMx) | process-tree parentage | partial (process spawned; cli-return consumer not verified) | #854 |
| acc:observe-and-correct:E005-SMOKE-001-full-shim-spawn-with-env-override | real (atdd-shim CLI) | env-var inheritance | N/A (single component) | — |
| acc:observe-and-correct:M005-SMOKE-001-real-observer-heartbeats-reach-coach | real (atdd observer + coach) | heartbeat delivery | both ends (emit + receive) | — |
| acc:observe-and-correct:M006-SMOKE-001-real-blocked-worker-reaches-coach | real (atdd observer + coach) | block event delivery | both ends (emit + receive) | — |
| acc:observe-and-correct:P001-SMOKE-002-observer-loop-closes | real (atdd observer CLI) | correction loop convergence | both ends (producer writes + convergence verified) | #825 |
| acc:observe-and-correct:P002-SMOKE-001-blocked-persona-triggers-correction | real (atdd spawn + observer) | correction trigger | both ends (drift → correction) | — |
| acc:observe-and-correct:R001-SMOKE-001-real-ask-answer-roundtrip | real (atdd observer + agent) | ask/answer protocol | both ends (ask + answer) | — |
| acc:spawn-agents:D002-SMOKE-001-session-convention-committed-and-loadable | real (git history + yaml load) | convention file | N/A (single component) | — |
| acc:spawn-agents:E004-SMOKE-001-shim-console-script-real-exit-codes | real (atdd-shim console script) | exit codes | N/A (single component) | — |
| acc:spawn-agents:E005-SMOKE-001-real-spawn-persona-completes-phase-transition | real (atdd spawn) | phase transition | both ends (spawn + transition) | — |
| acc:spawn-agents:E006-SMOKE-001-real-green-to-smoke-spawn-creates-persona | real (atdd spawn) | persona creation | N/A (single component) | — |
| acc:spawn-agents:E007-SMOKE-001-real-respawn-fresh-process-same-surface | real (atdd spawn) | fresh process | N/A (single component) | — |
| acc:spawn-agents:E008-SMOKE-001-interactive-tty-prompt-blocks-until-valid-input | real (atdd spawn + tty) | prompt blocking | N/A (single component) | — |
| acc:spawn-agents:E009-SMOKE-001-missing-env-var-produces-clear-adapter-error | real (atdd spawn) | error message | N/A (single component) | — |
| acc:spawn-agents:E010-SMOKE-001-readiness-gate-with-real-multiplexer | real (atdd spawn + cmux) | readiness gate | N/A (single component) | — |
| acc:spawn-agents:E011-SMOKE-001-verify-stage-with-real-multiplexer | real (atdd spawn + cmux) | stage verification | N/A (single component) | — |
| acc:spawn-agents:E012-SMOKE-001-atomic-rename-on-real-cmux | real (atdd spawn + cmux) | atomic rename | N/A (single component) | — |
| acc:spawn-agents:E013-SMOKE-001-live-adapter-registry-passes-layer-b-validator | real (atdd validate) | registry validation | N/A (validator) | — |
| acc:spawn-agents:E014-SMOKE-001-live-bash-auto-approve-no-stale-modal-reference | real (atdd spawn) | modal absence | N/A (single component) | — |
| acc:spawn-agents:E015-SMOKE-001-deployed-templates-contain-smoke-acceptance-checklist | real (template files) | file content | N/A (single component) | — |
| acc:spawn-agents:E016-SMOKE-001-no-popen-exec-failure-with-cli-return-env | real (atdd-shim CLI) | Popen success | N/A (single component) | — |
| acc:spawn-agents:E017-SMOKE-001-shim-invoked-via-same-python-as-coach | real (atdd spawn) | Python interpreter match | N/A (single component) | — |
| acc:spawn-agents:E018-SMOKE-001-live-spawn-pipeline-detects-dead-shim | real (atdd spawn) | dead shim detection | N/A (single component) | — |
| acc:spawn-agents:E019-SMOKE-001-shim-command-runtime-dir-is-absolute-in-live-spawn | real (_build_shim_command) | absolute path in --runtime-dir | N/A (single component) | — |
| acc:spawn-agents:E020-SMOKE-001-deployed-shim-resolves-relative-runtime-dir | real (atdd.coach.shim.__main__) | absolute path after normalization | N/A (single component) | — |
| acc:spawn-agents:E021-SMOKE-001-live-process-alive-message-names-polled-path | real (_verify_process_alive) | message content | N/A (single component) | — |
| acc:spawn-agents:L002-SMOKE-001-relative-runtime-root-output-log-at-absolute-path | real (cmd_spawn + fixture shim) | output.log location | N/A (single component) | — |
| acc:spawn-agents:L001-SMOKE-001-claude-code-no-modal-on-bash-read | real (atdd spawn + claude) | modal absence | N/A (single component) | — |
| acc:spawn-agents:M001-SMOKE-001-live-session-naming-apply-has-no-slash-rename | real (atdd spawn) | session name format | N/A (single component) | — |
| acc:spawn-agents:M002-SMOKE-001-live-observer-rules-pass-layer-b-validator | real (atdd validate) | rules validation | N/A (validator) | — |
| acc:spawn-agents:R001-SMOKE-001-live-bash-auto-approve-correction-references-escalate | real (atdd spawn + observer) | correction content | both ends (correction + escalation ref) | — |
| acc:spawn-agents:E022-SMOKE-001-live-claude-md-contains-no-atdd-skip-references | real (filesystem grep on CLAUDE.md) | ATDD_SKIP_* absent | N/A (single component) | #867 |
| acc:spawn-agents:E023-SMOKE-001-live-claude-md-line-count-within-budget | real (line count on filesystem CLAUDE.md) | ≤250 lines | N/A (single component) | #867 |
| acc:spawn-agents:E024-SMOKE-001-live-operator-emergency-bypass-doc-present-and-correct | real (filesystem read of docs/operator-emergency-bypass.md) | doc present + atdd emergency wording | N/A (single component) | #867 |
| acc:spawn-agents:R002-SMOKE-001-atdd-validate-coach-includes-size-budget-rule | real (direct import + call on live CLAUDE.md) | 0 size_budget violations, rule registered | N/A (meta-validator) | #867 |
| acc:spawn-agents:R003-SMOKE-001-atdd-validate-coach-includes-no-bypass-advertising-rule | real (direct import + call on live CLAUDE.md) | 0 no_bypass_advertising violations, rule registered | N/A (meta-validator) | #867 |
| acc:spawn-agents:L003-SMOKE-001-dispatched-agent-bash-log-contains-no-atdd-skip-invocations | real (agent bash log scan via ATDD_SMOKE_BASH_LOG) | ATDD_SKIP_* absent at runtime | N/A (single component) | #867 |
| acc:spawn-agents:E025-SMOKE-001-real-wagon-graph-output-present-and-well-formed | real (atdd repo graph --format launch-prompt) | exit 0, ≤2KB, wagon name, no traceback | N/A (single component) | — |
| acc:spawn-agents:E026-SMOKE-001-real-rendered-prompt-contains-graph-section | real (build_wagon_launch_prompt + _render_launch_prompt) | ## Wagon Architecture present, before ## Workflow | N/A (single component) | — |
| acc:spawn-agents:E027-SMOKE-001-atdd-validate-coach-passes-with-graph-section-present | real (atdd validate coach --local --skip-api) | zero coach.launch-prompt.must-include-wagon-graph violations | N/A (validator) | — |
| acc:spawn-agents:E028-SMOKE-001-live-adapter-registry-claude-code-has-surface-marker-probe | real (ADAPTER_REGISTRY inspection) | claude-code adapter has SurfaceMarkerProbe | N/A (single component) | #863 |
| acc:spawn-agents:E029-SMOKE-001-deployed-cmd-spawn-order-is-probe-then-paste-then-jsonl | real (cmd_spawn source inspection) | probe before paste before jsonl-wait | N/A (single component) | #863 |
| acc:spawn-agents:L004-SMOKE-001-session-jsonl-appears-after-launch-prompt-paste | real (cmd_spawn smoke) | session JSONL appears after paste | N/A (single component) | #863 |
| acc:mediate-worker-decisions:K001-SMOKE-001-live-ledger | real (JsonlPersistenceStore under .atdd) | commons:decision:record line present in the durable ledger | apply → DecisionLedger | #955 |
| acc:mediate-worker-decisions:L002-SMOKE-001-locates-live-blocked-agent | real (live Claude worker blocked on cmux Feed) | pending feed item located + mapped to a request with the live request_id | cmux Feed (feed.list/events) → sense | #955 |
| acc:mediate-worker-decisions:E003-SMOKE-001-unblocks-live-agent | real (live Claude worker + cmux rpc feed.*.reply) | coach verdict replied via Feed resolves the item; worker proceeds | mediate verdict → feed reply → agent | #955 |
| acc:mediate-worker-decisions:C003-SMOKE-001-live-dangerous-not-auto-approved | real (live worker requesting a dangerous tool use) | dangerous tool_input is not auto-replied; escalated to human soft-wait | safety gate over tool_input → no reply | #955; SKIPPED at runtime — no blocked dangerous permission inducible under cmux auto-mode (`--allow-dangerously-skip-permissions`); C003 unit+integration carry the guarantee |
| acc:mediate-worker-decisions:E012-SMOKE-001-coach-dispatch-drives-fixture-through-one-mediated-decision | real (live cmux + claude worker; single `atdd coach <fixture>` dispatch, no mocks, no human, no `cmux send`/TUI) | a real fixture issue advances from INIT through one mediated decision — proven by changed lifecycle state / a recorded decision, NOT a log line | dispatch → spawn worker (own workspace) → attach scoped feed_daemon → worker decision → daemon mediates → worker advances | #1025 (headline end-to-end smoke the closed #966/#967 never composed) |
| acc:mediate-worker-decisions:E013-SMOKE-001-dispatch-worker-decision-publishes-to-feed | real (worker spawned via the real dispatch worker-spawn path under live cmux + claude) | a dispatch-spawned worker's gated Bash decision appears as a pending item in cmux feed.list (publishes, not TUI-only) | dispatch fresh-spawn (own-workspace foreground launch) → worker Bash → cmux wrapper hook → feed.list | #1025 (producer half the closed #967 missed for the dispatch spawn path) |
| acc:consolidate-coach-workspace:E005-SMOKE-001-surface-workspace-resolves-without-invalid-handle | real (live cmux session + real worker surface in its own workspace) | surface_workspace returns a bare `workspace:N` handle with no `Invalid workspace handle` error; layout conformance applies | list-workspaces → handle sanitizer → list-panes → place_worker_surface_right | #1025 (layout handle parse bug; relates #601/#865) |
| acc:govern-lifecycle:E051-SMOKE-001-full-cycle-zero-projects-v2-graphql | real (IssueManager.update over a real manifest/config + recording GitHub client, no PROJECT_TOKEN) | a full RED→COMPLETE drive emits zero Projects-v2 board GraphQL; every transition is an `atdd:<phase>` label swap (REST) | issue.update → label REST swap; board methods asserted not-called | #1051 (decommission Projects v2; recording boundary verifies the negative — no board op is reachable) |
| acc:govern-lifecycle:E052-SMOKE-001-train-gate-enforces-offline-zero-board-graphql | real (Train gate over `.atdd/manifest.yaml` validated against `plan/_trains.yaml`) | the Train gate resolves the train from the manifest and enforces validity with zero `get_project_item_field_values` board read or fallback | manifest `_manifest_train` → validate vs plan/_trains.yaml | #1051 (offline train gate; board read deleted, no fallback) |
| acc:govern-lifecycle:E053-SMOKE-001-config-loads-and-github-imports-without-projects-v2 | real (live import of `atdd.integrations.github` + config load with no `project_id`) | `projects_v2` module is genuinely absent from shipped code; `integrations.github` exposes no projects_v2 attr; config loads cleanly without `project_id` | import surface + config loader (no board plumbing) | #1051 (substrate removal; real import/load, no mocks) |

---

## Histogram — Structural Bypass Cause

| structural-cause | count | description |
|---|---|---|
| synthetic-fixture / entry-point-bypass | 2 | Test drives a synthetic subprocess or direct class instantiation instead of the real CLI entry point (pre-retrofit) |
| synthetic→real (retrofitted) | 2 | Originally synthetic-fixture; retrofitted to real entry point by #855 |
| producer-only / handoff-gap | 2 | Test asserts on the producer side (artifact written) without verifying the consumer received it |
| real-entry-point / partial-handoff | 1 | Test drives real spawn but does not verify the full handoff path |
| real-entry-point / full-coverage | 22 | Test drives real entry point and verifies operator-observable behavior end-to-end |
| real-entry-point / single-component | 64 | Test drives real CLI entry point; asserts on single-component outcome (no cross-component handoff to verify) |
| real-entry-point / meta-validator | 16 | Test validates validator tooling itself (atdd validate, atdd rules, atdd repo graph) |

**Total classified:** 116 SMOKE acceptances (as of 2026-05-28)

### Cause definitions

- **synthetic-fixture / entry-point-bypass**: SMOKE test instantiates a class directly (`PersonaShim(`)
  or calls a subprocess with a synthetic command (`cat`, `sleep`, embedded Python script) rather than
  routing through the real CLI entry point (`atdd spawn`, `atdd coach`). The production wiring —
  `_inject_agent_env`, `_build_shim_command`, adapter command construction — is bypassed entirely.
  Root cause of **#854** (Popen crash invisible to synthetic E003-SMOKE tests).

- **producer-only / handoff-gap**: SMOKE test asserts only on the producer side (e.g., artifact
  written to `output.log` or `cli-return.jsonl`). When the feature has a producer→consumer handoff,
  the consumer side is never exercised. Test passes green even when the consumer is completely
  unwired. Root cause of **#824** (cli-return consumer never wired, SMOKE green because it only
  checked that the producer wrote the file).

- **real-entry-point / partial-handoff**: SMOKE test uses the real CLI entry point but does not
  verify the full end-to-end handoff. The process tree is correct but the correction delivery
  to the agent's stdin is not asserted.

- **real-entry-point / full-coverage**: SMOKE test drives the real CLI entry point and asserts
  on operator-observable behavior at both ends of the handoff. This is the canonical shape.

---

## Lived Incident Cross-Reference

| incident | issue | SMOKE that should have caught it | structural cause | bypass mechanism |
|---|---|---|---|---|
| cli-return consumer not wired | #824 | acc:observe-and-correct:E003-SMOKE-001 | producer-only / handoff-gap | SMOKE asserted producer wrote cli-return.jsonl; no consumer existed |
| shim swallows pty output | #843 | acc:observe-and-correct:E003-SMOKE-002 | synthetic-fixture + producer-only | SMOKE asserted on output.log; never checked operator-visible stdout |
| RED tests in consumer wheel | #846 | (no relevant SMOKE; coverage gap) | missing SMOKE | No SMOKE for "consumer entry points don't surface RED tests" |
| Shim Popen crashes on real command | #854 | acc:observe-and-correct:E003-SMOKE-001/002 | synthetic-fixture / entry-point-bypass | E003-SMOKE used Python stub; _inject_agent_env + _build_shim_command never called |

---

## Future Tracking

Post-retrofit regression metric. Expectation: zero post-SMOKE production bugs per release wave
from v3.83.0 onwards. Any non-zero entry must reference the root-cause issue and the WMBT
whose SMOKE test failed to catch it.

| release-wave | post-SMOKE-bugs | expectation | notes |
|---|---|---|---|
| v3.83.x | 0 | 0 | Baseline established after E028/E029 retrofit (issue #855) |
| v3.84.x | — | 0 | (pending) |
| v3.85.x | — | 0 | (pending) |

**Maintenance rule:** When a production bug is discovered after a SMOKE phase passed green,
add a row here with `post-SMOKE-bugs > 0`, link the root-cause issue, and identify which
WMBT SMOKE acceptance failed to catch it. Then author a new WMBT (or extend existing) to
tighten the coverage.

---

## Remediation Plan

| phase | action | WMBT |
|---|---|---|
| E028 GREEN | Extend smoke.convention.yaml with 3 anti-pattern rules | wmbt:govern-lifecycle:E028 |
| E028 GREEN | Create planner-side validator test_smoke_synthetic_fixture_bypass.py | wmbt:govern-lifecycle:E028 |
| E029 GREEN | Retrofit test_e003_smoke_001 to use real atdd spawn path | wmbt:govern-lifecycle:E029 |
| E029 GREEN | Retrofit test_e003_smoke_002 to remove _SYNTHETIC_AGENT | wmbt:govern-lifecycle:E029 |
| E029 GREEN | Remove ATDD_RUN_SMOKE=1 opt-in gate from test_e004_smoke_001 | wmbt:govern-lifecycle:E029 |
| L002 GREEN | Implement walk_all_smoke_acceptances_for_anti_patterns meta-walker | wmbt:govern-lifecycle:L002 |
