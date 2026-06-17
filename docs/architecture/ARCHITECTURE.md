# Architecture — Remotive Behavioral Model Compiler

## Module Breakdown

```text
remotive-bm-compiler/
├── bmgen/                          # Main Python package
│   ├── __init__.py                  # Package marker
│   ├── cli.py                       # CLI entry point (argparse + subcommands)
│   │
│   ├── ir/                          # Intermediate Representation layer
│   │   ├── __init__.py
│   │   ├── model.py                 # All IR dataclass definitions
│   │   ├── validators.py            # Invariant validation logic
│   │   └── parser.py                # YAML → raw spec dict parsing
│   │   └── builder.py               # Raw spec dict → validated BehavioralModelIR
│   │
│   ├── recipes/                     # Pattern recipe registry
│   │   ├── __init__.py
│   │   ├── registry.py              # RecipeRegistry: name → Recipe lookup
│   │   ├── base.py                  # Abstract Recipe base class
│   │   ├── direct_signal_mapping.py # DirectSignalMapping recipe (P0)
│   │   ├── toggle_button_state.py   # ToggleButtonState recipe (P0)
│   │   ├── periodic_blinking_output.py # PeriodicBlinkingOutput recipe (P1)
│   │
│   ├── compiler/                    # Code generation layer
│   │   ├── __init__.py
│   │   ├── python_generator.py      # Orchestrates template rendering per handler
│   │   ├── context_builder.py       # IR + Recipe → Jinja2 template context dicts
│   │   ├── templates/               # Jinja2 template files
│   │   │   ├── main.py.j2           # Top-level behavioral model template
│   │   │   ├── handler_direct.py.j2 # Handler method template for DirectSignalMapping
│   │   │   ├── handler_toggle.py.j2 # Handler method template for ToggleButtonState
│   │   │   ├── handler_blink.py.j2  # Handler method template for PeriodicBlinkingOutput
│   │   │   ├── handler_reset.py.j2  # Reboot/reset handler template
│   │   │   ├── test_handler.py.j2   # Test file template for behavioral verification
│   │
│   ├── verifier/                    # 3-layer verification system
│   │   ├── __init__.py
│   │   ├── structural.py            # T1: Structural verification
│   │   ├── behavioral.py            # T2: Behavioral verification
│   │   ├── composition.py           # T3: Composition verification
│   │   ├── report.py                # VerificationReport JSON generation
│   │   ├── runner.py                # Orchestrates T1 → T2 → T3 sequence
│   │
│   ├── config/                      # Configuration and constants
│   │   ├── __init__.py
│   │   ├── defaults.py              # Default values (imports, namespace patterns)
│   │
├── examples/                        # Example YAML spec files
│   ├── bcm_direct.yaml              # DirectSignalMapping example
│   ├── bcm_toggle.yaml              # ToggleButtonState example
│   ├── bcm_blinking.yaml            # PeriodicBlinkingOutput example
│
├── tests/                           # Test suite
│   ├── test_ir_validation.py        # IR invariant validation tests
│   ├── test_compile_direct_mapping.py # DirectSignalMapping generation tests
│   ├── test_compile_toggle.py       # ToggleButtonState generation tests
│   ├── test_verify_structural.py    # T1 structural verifier tests
│   ├── test_verify_behavioral.py    # T2 behavioral verifier tests
│   ├── test_verify_composition.py   # T3 composition verifier tests
│   ├── conftest.py                  # Shared test fixtures (fake Frame, mock restbus)
│
├── docs/
│   └── architecture/                # This document set
│
├── .github/
│   └── workflows/
│       └── verify.yml               # CI: bmgen verify workflow
│
├── pyproject.toml                   # Package configuration
├── README.md                        # Project overview
```

## Package Responsibilities

### `bmgen.ir` — Intermediate Representation

**Purpose**: Parse YAML specs into validated, typed intermediate representation.

| Module | Responsibility |
|--------|---------------|
| `parser.py` | Read YAML file → raw Python dict. No validation; just parsing. |
| `model.py` | Define all IR dataclasses (`BehavioralModelIR`, `HandlerIR`, etc.). Pure data, no behavior. |
| `validators.py` | Check all IR invariants (unique names, namespace existence, state ownership, etc.). Returns list of violations. |
| `builder.py` | Take raw spec dict → construct IR dataclasses → run validators → return validated `BehavioralModelIR` or raise on violations. |

**Boundary rule**: `ir/` never imports from `compiler/`, `recipes/`, or `verifier/`. It is a pure data + validation layer.

### `bmgen.recipes` — Pattern Recipe Registry

**Purpose**: Provide known behavior patterns that the compiler can apply deterministically.

| Module | Responsibility |
|--------|---------------|
| `base.py` | Abstract `Recipe` class with `name`, `validate(ir_handler)`, `build_context(ir_handler)` methods. |
| `registry.py` | `RecipeRegistry` class: flat dict mapping pattern name → Recipe instance. `get(name)` lookup. `list_all()` for discovery. |
| `direct_signal_mapping.py` | Recipe for "read signal X → write same value to signals Y1, Y2, ... via restbus.update_signals". Validates: exactly one input, at least one output, no state needed. |
| `toggle_button_state.py` | Recipe for "read button signal → toggle boolean state → write state to outputs". Validates: exactly one input, at least one output, one boolean state field. |
| `periodic_blinking_output.py` | Recipe for "state enables blinking → periodic async ticker → cleanup on exit". Validates: has state, has periodic task, has cleanup declaration. |

**Boundary rule**: `recipes/` reads from `ir/` (it validates `HandlerIR` instances) but never writes to IR. It produces `context dicts` (plain Python dicts) that the compiler consumes. It never imports from `compiler/` or `verifier/`.

### `bmgen.compiler` — Deterministic Code Generator

**Purpose**: Generate Remotive Behavioral Model Python code from IR + recipe contexts using Jinja2 templates.

| Module | Responsibility |
|--------|---------------|
| `context_builder.py` | Take `BehavioralModelIR` + recipe contexts → build a single unified template context dict with all data needed for rendering. |
| `python_generator.py` | Load Jinja2 templates → render with context → write Python files to output directory. Orchestrates per-handler and per-model rendering. |

**Template responsibilities**:
- `main.py.j2`: Generates the complete behavioral model file (imports, dataclass/class definition, namespace setup, handler methods, `main()` function, `__main__` entry point)
- `handler_*.py.j2`: Generates individual handler method bodies (signal extraction, logic, `restbus.update_signals` calls)
- `handler_reset.py.j2`: Generates `on_reboot` handler that resets all owned states and calls `restbus.reset()`
- `test_handler.py.j2`: Generates test file with fake Frame and mock restbus for behavioral verification

**Boundary rule**: `compiler/` reads from `ir/` and `recipes/`. It writes to the filesystem (generated Python files). It never imports from `verifier/`.

### `bmgen.verifier` — 3-Layer Verification System

**Purpose**: Verify generated Python code at three layers (structural, behavioral, composition).

| Module | Responsibility |
|--------|---------------|
| `structural.py` | T1 checks: file exists, syntax valid, imports succeed, handler async, handler accepts frame, namespace refs valid, restbus support, FrameFilter matching |
| `behavioral.py` | T2 checks: fake Frame → call handler → check mock restbus output. Per-pattern behavioral tests. |
| `composition.py` | T3 checks: no duplicate handlers, no duplicate state ownership, no pattern conflicts, periodic cleanup, reset coverage, lifecycle validity |
| `report.py` | Aggregate all check results into `VerificationReport` JSON. PASS/FAIL semantics. |
| `runner.py` | Run T1 → T2 → T3 in sequence. T1 must PASS before T2 runs. T2 must PASS before T3 runs. Fail-fast on layer failure. |

**Boundary rule**: `verifier/` reads generated Python files (filesystem) and reads from `ir/` (for expected behavior specs). It never imports from `compiler/` or `recipes/`.

### `bmgen.cli` — Command Line Interface

**Purpose**: Provide `bmgen generate` and `bmgen verify` commands.

| Command | Pipeline |
|---------|----------|
| `bmgen parse <yaml>` | YAML → parser → builder → validated IR (print to stdout) |
| `bmgen generate <yaml> --out <dir>` | YAML → IR → recipe validation → compiler → generated Python files |
| `bmgen verify <dir>` | Load generated dir → T1 → T2 → T3 → verification report JSON |
| `bmgen recipes` | List all available recipes |

**Boundary rule**: `cli.py` is the orchestrator. It calls into `ir/`, `recipes/`, `compiler/`, `verifier/` in sequence but contains no business logic itself.

## Boundary Summary

```text
YAML file
  │
  ▼
bmgen.ir.parser ──► raw spec dict
  │
  ▼
bmgen.ir.builder ──► BehavioralModelIR (validated by bmgen.ir.validators)
  │
  ▼
bmgen.recipes.registry ──► recipe.validate(handler_ir) ──► context dicts
  │
  ▼
bmgen.compiler.context_builder ──► unified template context
  │
  ▼
bmgen.compiler.python_generator ──► Jinja2 templates ──► generated Python files
  │
  ▼
bmgen.verifier.runner ──► T1 ──► T2 ──► T3 ──► VerificationReport JSON
```

**Key boundaries**:
- `ir/` is a **pure data layer**: no imports from compiler, recipes, or verifier
- `recipes/` is a **validation + context layer**: reads IR, produces dicts, no filesystem writes
- `compiler/` is a **generation layer**: reads IR + recipe contexts, writes filesystem
- `verifier/` is a **checking layer**: reads filesystem + IR, writes report, never generates code

## Why This Is NOT GraphRAG

**GraphRAG** (Graph-based Retrieval-Augmented Generation) is a pattern where:
1. A knowledge graph stores entities and relationships
2. An LLM retrieves relevant subgraphs at query time
3. The LLM generates responses conditioned on retrieved graph data

This architecture is **fundamentally different**:

| Aspect | GraphRAG | This Architecture |
|--------|----------|-------------------|
| Knowledge store | Neo4j / vector DB | Flat Python dict (recipe registry) |
| Retrieval | Semantic search / embedding match | Exact name lookup (`registry.get("DirectSignalMapping")`) |
| Generation | LLM generates text | Jinja2 template renders deterministic code |
| Reasoning | LLM chains-of-thought | Recipe logic (pure Python functions) |
| Variability | Non-deterministic (LLM temperature) | Deterministic (same YAML → same code always) |
| Verification | Post-hoc LLM review | Pre-defined invariant checks (T1/T2/T3) |

The recipe registry is a **flat lookup table**, not a graph database. It maps pattern names to Python classes, not semantic entities to vector embeddings. The compiler is a **template renderer**, not an LLM.

## Why Agent/RAG Is Future Layer Only

**Current MVP rationale**: The MVP must be deterministic and verifiable. Agent-generated code and RAG-based retrieval introduce non-determinism that cannot be verified by T1/T2/T3 checks.

**Future layer rationale**: When the recipe registry grows to dozens of patterns, and when users need to compose patterns in novel ways, an Agent/RAG layer can assist with:
1. **Pattern discovery**: Mining existing behavioral models for new recipe candidates (RAG over code corpus)
2. **Novel logic assistance**: When a YAML spec is marked `novel_logic`, an Agent can propose new recipe definitions (but these must be reviewed and codified before entering the registry)
3. **MCP integration**: A Claude Code MCP server can provide interactive model generation in IDEs

These are **augmentation layers**, not core pipeline layers. The deterministic compiler + verifier must work standalone. Agent/RAG layers wrap around it, not replace it.

**The invariant is**: No line of generated Python code in the CI path comes from an LLM. All code comes from templates + recipe logic. Agent assistance may help *write recipes* or *write YAML specs*, but the compiler path remains deterministic.
