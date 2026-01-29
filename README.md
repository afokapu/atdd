# ATDD

Acceptance Test Driven Development toolkit for structured planning and convention enforcement.

## Installation

### From GitHub (recommended for now)

```bash
pip install git+https://github.com/afokapu/atdd.git
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

### Future: PyPI

Once published to PyPI:
```bash
pip install atdd
```

## Quick Start

```bash
# Initialize ATDD in your project
atdd init

# Create a planning session
atdd session new my-feature

# List sessions
atdd session list

# Run validators
atdd --test all
```

## What It Does

ATDD provides:

1. **Session Management** - Structured planning documents with templates and tracking
2. **Convention Enforcement** - YAML-based conventions validated via pytest
3. **ATDD Lifecycle** - Planner → Tester → Coder phase gates

## Commands

### Project Initialization

```bash
atdd init              # Create atdd-sessions/ and .atdd/ directories
atdd init --force      # Reinitialize (overwrites existing)
```

Creates:
```
your-project/
├── atdd-sessions/
│   ├── SESSION-TEMPLATE.md
│   └── archive/
└── .atdd/
    └── manifest.yaml
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
│   ├── schemas/           # JSON schemas
│   ├── templates/         # Session templates
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
