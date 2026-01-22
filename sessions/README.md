# Session Plans

Design planning sessions for ATDD implementation work.

---

## Quick Start

1. **Rename conversation:** `/rename SESSION-{NN}-{slug}`
2. **Copy template:** `cp SESSION-TEMPLATE.md SESSION-{NN}-{slug}.md`
3. **Fill ALL sections** (even if N/A - write "N/A" explicitly)
4. **Set status to INIT**
5. **Update status as you progress:** INIT → PLANNED → ACTIVE → COMPLETE

---

## Convention Reference

**Convention file:** `atdd/coach/conventions/session.convention.yaml`
**Template file:** `sessions/SESSION-TEMPLATE.md`

---

## Session Types

| Type | Description | Focus |
|------|-------------|-------|
| `implementation` | Building new features via ATDD cycle | WMBT decomposition, RED→GREEN→REFACTOR |
| `migration` | Moving from one architecture to another | Before/after diagrams, ripple effects |
| `refactor` | Improving code without changing behavior | Problem statement, test preservation |
| `analysis` | Investigation and discovery work | Findings, recommendations, evidence |
| `planning` | Designing approach before implementation | Design decisions, scope definition |
| `cleanup` | Removing tech debt or fixing violations | Issue inventory, validation gates |
| `tracking` | Ongoing progress log across sessions | Chronological log, metrics |

---

## Status Values

| Status | Description | Next States |
|--------|-------------|-------------|
| `INIT` | Session created, scope being defined | PLANNED, OBSOLETE |
| `PLANNED` | Scope locked, phases defined | ACTIVE, OBSOLETE |
| `ACTIVE` | Work in progress | BLOCKED, COMPLETE, OBSOLETE |
| `BLOCKED` | Cannot proceed, dependency needed | ACTIVE, OBSOLETE |
| `COMPLETE` | All success criteria met | (terminal) |
| `OBSOLETE` | Superseded by another session | (terminal) |

---

## Infrastructure Archetypes

| ID | Description | Artifacts |
|----|-------------|-----------|
| `db` | Supabase PostgreSQL + JSONB | `supabase/migrations/*.sql` |
| `be` | Python FastAPI 4-layer | `python/{wagon}/{feature}/src/` |
| `fe` | TypeScript/Preact 4-layer | `web/src/{wagon}/{feature}/` |
| `contracts` | JSON Schema contracts | `contracts/{domain}/*.schema.json` |
| `wmbt` | What Must Be True criteria | `plan/{wagon}/*.yaml` |
| `wagon` | Bounded context module | `plan/{wagon}/_*.yaml` |
| `train` | Release orchestration | `plan/_trains.yaml` |
| `telemetry` | Observability artifacts | `telemetry/*.yaml` |
| `migrations` | Database schema evolution | `supabase/migrations/*.sql` |

---

## Mandatory Sections

Every session file MUST have ALL of these sections:

| Section | Description |
|---------|-------------|
| **Header** | Title, Date, Status, Branch, Type, Complexity, Archetypes |
| **Context** | Problem Statement, User Impact, Root Cause |
| **Scope** | In Scope, Out of Scope, Dependencies |
| **Architecture** | Conceptual Model, Before State, After State, Data Model |
| **Phases** | Ordered work breakdown with gates and deliverables |
| **Progress** | Progress Tracker table, WMBT Status (if implementation) |
| **Validation** | Gate Commands, Success Criteria |
| **Decisions** | Questions faced and choices made |
| **Session Log** | Chronological work diary |
| **Artifacts** | Created, Modified, Deleted files |
| **Related** | Related Sessions, Related WMBTs |
| **Notes** | Additional context |

**Rule:** If a section doesn't apply, write "N/A" explicitly. Never omit sections.

---

## Rules

### Creation
1. Use next available session number
2. Copy `SESSION-TEMPLATE.md` and fill ALL sections
3. Set status to `INIT`
4. Create branch if needed

### Progression
1. Update status on state transitions
2. Log all work in Session Log section
3. Run gate commands before marking phase DONE
4. Update Progress Tracker after each work item

### Completion
1. All success criteria must be checked
2. All phases must be DONE or SKIPPED with rationale
3. Set status to `COMPLETE`
4. Rename file to indicate completion:
   - `SESSION-36-atdd-validator-fixes-(completed).md` or
   - `SESSION-36-atdd-validator-fixes-✅.md`
5. Move to `archive/` after 1 week

### Blocking
1. Document blocker in Session Log
2. Set status to `BLOCKED`
3. Create dependency link if blocked by another session

### Obsolete
1. Add warning banner at top of file
2. Link to superseding session
3. Set status to `OBSOLETE`

---

## Validation

```bash
# Validate session files against convention
python3 -m pytest atdd/coach/validators/test_session_*.py -v
```

---

## Active Sessions

| # | File | Type | Status | Focus |
|---|------|------|--------|-------|
| 27 | SESSION-27-realtime-latency-fix.md | implementation | ACTIVE | Decision submission latency |
| 31 | SESSION-31-timebank-persistence.md | refactor | PLANNED | Event sourcing timebank |
| 34 | SESSION-34-persona-bot-separation.md | refactor | PLANNED | Persona/bot terminology |
| 37 | SESSION-37-contract-alignment.md | cleanup | ACTIVE | Contract schema alignment |

---

## Archived Sessions

All complete sessions are in `archive/` with `-(completed)` suffix.

| # | Name | Type | Summary |
|---|------|------|---------|
| 01-19 | Various | Various | See archive/ |
| 20 | janet-ui-refactor | refactor | Janet physically-reactive UI |
| 21 | live-mode | implementation | Live mode feature |
| 22 | bot-opponent-system | implementation | Bot opponent system |
| 23 | elo-score-engine | implementation | ELO scoring |
| 24 | global-leaderboard | implementation | Leaderboard feature |
| 25 | multilingual-scenarios | implementation | Multilingual fragments |
| 25 | player-profile-match | implementation | Player profile in match |
| 26 | elo-wiring-integration | implementation | ELO update integration |
| 28 | bot-wiring | implementation | Bot opponent wiring |
| 29 | station-master-pattern | refactor | Station master pattern |
| 30 | bot-wiring-complete | implementation | Bot wiring completion |
| 32 | pwa-implementation | feature | PWA for iOS/Android |
| 33 | narrative-fragments | feature | Narrative fragments |
| 35 | fragment-type-routing | implementation | Fragment type routing |
| 36 | atdd-validator-fixes | cleanup | ATDD validator fixes |
| 38 | occupation-classification | implementation | ESCO occupation mapping |
