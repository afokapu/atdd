# ATDD Platform

A unified Acceptance Test-Driven Development (ATDD) framework that orchestrates planning, testing, and implementation validation through a single CLI.

## Problem

Agentic coding breaks down when instructions are ambiguous. It took dozens of iterations to reach a workflow where I could trust that agents would follow good practice, preserve standards, and keep the codebase understandable.

## Solution

ATDD provides a structured flow and a meta-validation layer to keep artifacts coherent:

```
Session (user need)
  ↓
Plan (requirements)
  ↓
Tests (contracts + acceptance criteria)
  ↓
Code implementation
  ↓
Refactor
  ↓
Meta-validation (conventions + schemas)
  ↺ feeds back into coherence checks
```

Note: The default stack assumes Python for validation, pytest for execution, and YAML/JSON Schema for conventions. It can be adapted to any stack with comparable capabilities.

## Quick start

```bash
# Show available commands
./atdd/atdd.py --help

# Status summary
./atdd/atdd.py --status

# Generate repository inventory
./atdd/atdd.py --inventory

# Run all validators
./atdd/atdd.py --test all

# Fast smoke run
./atdd/atdd.py --quick
```

## What it does

- One CLI entry point (the coach) for inventory and validation.
- Auto-discovered pytest validators across planner, tester, coder, and coach phases.
- Conventions + schemas per phase to enforce structure and traceability.
- Cross-phase registry checks and lifecycle coordination.

## Repository layout

```
atdd/
  atdd.py            # CLI entry point (coach)
  coach/             # Cross-phase coordination and commands
  planner/           # Planning conventions, schemas, validators
  tester/            # Testing conventions, schemas, validators
  coder/             # Implementation conventions, validators
```

## Validators

Validators are standard pytest tests named `test_*.py` and are auto-discovered.
Add a new validator under `atdd/{phase}/validators/` and run:

```bash
./atdd/atdd.py --test <phase>
```

## Documentation

- `atdd/README.md` - Full command reference and detailed architecture
- `sessions/` - Session notes and migration progress
- `atdd/*/conventions/` - Phase rules (YAML)
- `atdd/*/schemas/` - Phase schemas (JSON Schema)

## License

See `LICENSE`.
