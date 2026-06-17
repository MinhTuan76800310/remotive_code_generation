# Remotive Behavioral Model Compiler

A deterministic compiler that generates Remotive Behavioral Model Python code from YAML specs, with 3-layer verification.

## Quick Start

```bash
pip install -e ".[dev]"

# Generate a behavioral model from a YAML spec
bmgen generate examples/bcm_direct.yaml --out generated/

# Verify the generated code
bmgen verify generated/

# List available recipes
bmgen recipes
```

## Architecture

See [docs/architecture/](docs/architecture/) for the full architecture document set:

- [MVP_PLAN.md](docs/architecture/MVP_PLAN.md) — Problem statement, goals, scope, milestones
- [ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) — Module breakdown, boundaries, design rationale
- [WORKFLOW.md](docs/architecture/WORKFLOW.md) — Developer workflow, CLI usage, CI
- [DATAFLOW.md](docs/architecture/DATAFLOW.md) — End-to-end dataflow with Mermaid diagrams
- [IR_SCHEMA.md](docs/architecture/IR_SCHEMA.md) — Typed IR, YAML schema, validation rules
- [VERIFIER_DESIGN.md](docs/architecture/VERIFIER_DESIGN.md) — 3-layer verifier design

## License

MIT
