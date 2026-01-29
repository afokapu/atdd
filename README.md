# ATDD

Acceptance Test Driven Development toolkit for structured planning and convention enforcement.

## Installation

### From PyPI

```bash
pip install atdd
```

### Upgrade

```bash
pip install --upgrade atdd
```

### For Development

```bash
# Clone the repo
git clone https://github.com/afokapu/atdd.git
cd atdd

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Verify installation
atdd --help
```

## Quick Start

```bash
atdd init                      # Initialize ATDD in your project
atdd gate                      # ⚠️ START EVERY SESSION WITH THIS
atdd session new my-feature    # Create a planning session
atdd sync                      # Sync rules to agent config files
atdd --test all                # Run validators
```

> **⚠️ `atdd gate` is required.** 
> 🤖 Tell your agent: "Run `atdd gate` and follow ATDD rigorously." 
> Agents skip instruction files but can't ignore tool output. No gate = no ATDD guarantees.

## What It Does

ATDD provides:

1. **Session Management** - Structured planning documents with templates and tracking
2. **Convention Enforcement** - YAML-based conventions validated via pytest
3. **ATDD Lifecycle** - Planner → Tester → Coder phase gates
4. **Agent Config Sync** - Keep ATDD rules in sync across AI agent config files

## Commands

### Project Initialization

```bash
atdd init              # Create atdd-sessions/, .atdd/, and CLAUDE.md
atdd init --force      # Reinitialize (overwrites existing)
```

Creates:
```
your-project/
├── CLAUDE.md              # With managed ATDD block
├── atdd-sessions/
│   ├── SESSION-TEMPLATE.md
│   └── archive/
└── .atdd/
    ├── manifest.yaml      # Session tracking
    └── config.yaml        # Agent sync configuration
```

### Session Management

```bash
atdd session new <slug>                 # Create new session
atdd session new <slug> --type <type>   # Specify type
atdd session list                       # List all sessions
atdd session archive <id>               # Archive session
atdd session sync                       # Sync manifest with files
```

Session types: `implementation`, `migration`, `refactor`, `analysis`, `planning`, `cleanup`, `tracking`

### Agent Config Sync

Sync ATDD rules to agent config files using managed blocks that preserve user content:

```bash
atdd sync                  # Sync all enabled agents from config
atdd sync --agent claude   # Sync specific agent only
atdd sync --verify         # Check if files are in sync (for CI)
atdd sync --status         # Show sync status for all agents
```

Supported agents:
| Agent | File |
|-------|------|
| claude | CLAUDE.md |
| codex | AGENTS.md |
| gemini | GEMINI.md |
| qwen | QWEN.md |

Configure which agents to sync in `.atdd/config.yaml`:
```yaml
version: "1.0"
sync:
  agents:
    - claude      # Enabled by default
    # - codex     # Uncomment to sync AGENTS.md
    # - gemini    # Uncomment to sync GEMINI.md
    # - qwen      # Uncomment to sync QWEN.md
```

**Multi-agent setup:** To use multiple agents with consistent rules, enable them all in config and run sync:

```yaml
sync:
  agents:
    - claude
    - codex
    - gemini
    - qwen
```

```bash
atdd sync  # Creates/updates CLAUDE.md, AGENTS.md, GEMINI.md, QWEN.md
```

### ATDD Gate (Bootstrap Protocol)

Agents often skip instruction files. The gate solves this by injecting rules via mandatory tool output.

**Protocol:**

1. Run this command first:
   ```bash
   atdd gate
   ```

2. Agent must paste output and confirm:
   - Which file(s) were loaded
   - The reported hash
   - The key constraints

3. If files are missing/unsynced:
   ```bash
   atdd sync
   atdd gate  # Re-verify
   ```

**Example output:**
```
============================================================
ATDD Gate Verification
============================================================

Loaded files:
  - CLAUDE.md (hash: d04f897c6691dc13...)

Key constraints:
  1. No ad-hoc tests - follow ATDD conventions
  2. Domain layer NEVER imports from other layers
  3. Phase transitions require quality gates

------------------------------------------------------------
Before starting work, confirm you have loaded these rules.
------------------------------------------------------------
```

**Why this works:**
- Gate output is mandatory tool output - agent can't ignore it
- Proves which ATDD files were actually loaded
- Forces consistency across all agents

**Rule:** If ATDD rules matter, start with `atdd gate`. No gate = no guarantees.

### Validation

```bash
atdd --test all        # Run all validators
atdd --test planner    # Planning artifacts only
atdd --test tester     # Testing artifacts only
atdd --test coder      # Implementation only
atdd --quick           # Fast smoke test
```

### Other Commands

```bash
atdd --status          # Platform status
atdd --inventory       # Generate artifact inventory
atdd --help            # Full help
```

## Project Structure

```
src/atdd/
├── cli.py                 # Entry point
├── coach/
│   ├── commands/          # CLI command implementations
│   ├── conventions/       # Coach conventions (YAML)
│   ├── overlays/          # Agent-specific additions
│   ├── schemas/           # JSON schemas
│   ├── templates/         # Session templates, ATDD.md
│   └── validators/        # Coach validators
├── planner/
│   ├── conventions/       # Planning conventions
│   ├── schemas/           # Planning schemas
│   └── validators/        # Planning validators
├── tester/
│   ├── conventions/       # Testing conventions
│   ├── schemas/           # Testing schemas
│   └── validators/        # Testing validators
└── coder/
    ├── conventions/       # Coding conventions
    ├── schemas/           # Coder schemas
    └── validators/        # Implementation validators
```

## Development

### Setup

```bash
git clone https://github.com/afokapu/atdd.git
cd atdd
pip install -e ".[dev]"
```

### Run Tests

```bash
# All tests
pytest

# Specific phase
pytest src/atdd/planner/validators/

# With coverage
pytest --cov=atdd --cov-report=html
```

### Adding Validators

1. Create `src/atdd/{phase}/validators/test_{name}.py`
2. Write pytest test functions
3. Run `atdd --test {phase}`

Validators are auto-discovered by pytest.

### Adding Conventions

1. Create `src/atdd/{phase}/conventions/{name}.convention.yaml`
2. Reference in validators via `Path(__file__).parent.parent / "conventions" / "..."`

## Requirements

- Python 3.10+
- pyyaml

Dev dependencies: pytest, pytest-xdist

## License

MIT
