# Architecture — Remotive Behavioral Model Compiler

> **Schema version**: `service_oriented` (namespace_types + multi-output handlers)
> **Last updated**: 2026-07-06

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
│   │   ├── validators.py            # Invariant validation logic (16 rules)
│   │   ├── parser.py                # YAML → raw spec dict parsing
│   │   └── builder.py               # Raw spec dict → validated BehavioralModelIR
│   │
│   ├── recipes/                     # Pattern recipe registry (9 recipes)
│   │   ├── __init__.py
│   │   ├── registry.py              # RecipeRegistry: name → Recipe lookup
│   │   ├── base.py                  # Abstract Recipe base class
│   │   ├── direct_signal_mapping.py # DirectSignalMapping recipe (P0)
│   │   ├── toggle_button_state.py   # ToggleButtonState recipe (P0)
│   │   ├── periodic_blinking_output.py # PeriodicBlinkingOutput recipe (P1)
│   │   ├── threshold_mapping.py     # ThresholdMapping recipe (P1)
│   │   ├── logic_gate.py            # LogicAnd/Or/Xor/Not recipe (P1)
│   │   ├── websocket_bridge.py      # WebsocketBridge recipe (model-level)
│   │
│   ├── compiler/                    # Code generation layer
│   │   ├── __init__.py
│   │   ├── python_generator.py      # Orchestrates template rendering per handler
│   │   ├── context_builder.py       # IR + Recipe → Jinja2 template context dicts
│   │   ├── templates/               # Jinja2 template files
│   │   │   ├── main.py.j2           # Top-level behavioral model template
│   │   │   ├── handler_direct.py.j2 # Handler for DirectSignalMapping / ThresholdMapping
│   │   │   ├── handler_toggle.py.j2 # Handler for ToggleButtonState
│   │   │   ├── handler_logic.py.j2  # Handler for LogicAnd/Or/Xor/Not
│   │   │   ├── handler_blink.py.j2  # Handler for PeriodicBlinkingOutput
│   │   │   ├── handler_websocket.py.j2 # Model-level websocket listener
│   │   │   ├── handler_weighted.py.j2  # WeightedLogOdds (CAD fan-in, latched inputs)
│   │   │   ├── handler_reset.py.j2  # Reboot/reset handler
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
│   ├── test_ir_validation.py        # IR invariant validation tests (incl. rules 14-16)
│   ├── test_compile_direct_mapping.py # DirectSignalMapping generation tests
│   ├── test_threshold_mapping.py    # ThresholdMapping + operator/direction tests
│   ├── test_multi_output.py         # Multi-output handler fan-out tests
│   ├── test_websocket_bridge.py     # WebsocketBridge tests
│   ├── test_verify_generated.py     # Verifier integration tests
│   ├── conftest.py                  # Shared test fixtures (fake Frame, mock restbus)
│
├── docs/
│   └── architecture/                # This document set
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
| `model.py` | Define all IR dataclasses (`BehavioralModelIR`, `HandlerIR`, `OutputGroupIR`, `WebsocketListenerIR`, etc.). Pure data, no behavior. |
| `validators.py` | Check all IR invariants (16 rules: unique names, namespace existence, output restbus, state ownership, namespace_types schema, etc.). Returns list of violations. Also provides `validate_namespace_types(spec, ir)` for schema-level checks that need the raw spec. |
| `builder.py` | Take raw spec dict → construct IR dataclasses → infer namespaces → run validators → return validated `BehavioralModelIR` or raise on violations. |

**Boundary rule**: `ir/` never imports from `compiler/`, `recipes/`, or `verifier/`. It is a pure data + validation layer.

#### Key architectural change (service_oriented): Namespace Inference

The old schema required users to explicitly declare every namespace with `role`, `type`, and `restbus` fields in a top-level `namespaces:` list. This was verbose and error-prone — the role and restbus are derivable from which handlers reference the namespace.

The new `_infer_namespaces()` algorithm:
1. **Collects refs** from every handler's `input_namespace`, every `output_group.namespace`, and every websocket listener's `output_namespace`
2. **Derives role**: `"both"` if referenced as both input and output; `"input"` if only as input; `"output"` if only as output
3. **Auto-creates restbus**: `RestbusConfigIR(sender_filter=ecu_name)` for any namespace with role `"output"` or `"both"`
4. **Reads type from `namespace_types:` map**: a flat `name → type` mapping in the YAML

The old `namespaces:` block is deprecated but still accepted during migration — it emits a `DeprecationWarning` and the inference path still runs.

### `bmgen.recipes` — Pattern Recipe Registry

**Purpose**: Provide known behavior patterns that the compiler can apply deterministically.

| Module | Responsibility |
|--------|---------------|
| `base.py` | Abstract `Recipe` class with `name`, `description`, `template_name`, `validate()`, `build_context()`, `output_value_expr()`, `required_fields()`. |
| `registry.py` | `RecipeRegistry` class: flat dict mapping pattern name → Recipe instance. `get(name)` lookup. `known_patterns()` returns set of all registered names (single source of truth for Invariant 9). |
| `direct_signal_mapping.py` | Recipe for "read signal X → write same value to signals Y1, Y2, ... via restbus.update_signals". |
| `toggle_button_state.py` | Recipe for "read button signal → toggle boolean state → write state to outputs". |
| `periodic_blinking_output.py` | Recipe for "state enables blinking → periodic async ticker → cleanup on exit". |
| `threshold_mapping.py` | Recipe for "compare analog input against threshold → output boolean 0/1". Supports configurable operator (`>`, `>=`, `<`, `<=`, `==`, `!=`) and direction (`above`/`below`). |
| `logic_gate.py` | Recipe for stateless boolean logic: `LogicAnd`, `LogicOr`, `LogicXor`, `LogicNot`. Reads 2 input signals (1 for NOT), applies gate, writes result. |
| `websocket_bridge.py` | Model-level recipe (not per-handler): bridges an external websocket JSON stream onto a CAN output namespace's restbus. Validates `WebsocketListenerIR` not `HandlerIR`. |
| `weighted_log_odds.py` | **WeightedLogOdds** (CAD): latch bool inputs from multiple namespaces/frames, compute `Σ wᵢ·bool(inputᵢ)`, compare to `threshold`, write 0/1 to outputs. Registers N `create_input_handler` calls to one method. Internal latch fields (`_*_latched`) — no user `state:`. |

**9 registered patterns**: DirectSignalMapping, ToggleButtonState, PeriodicBlinkingOutput, ThresholdMapping, LogicAnd, LogicOr, LogicXor, LogicNot, WebsocketBridge, **WeightedLogOdds**

**Boundary rule**: `recipes/` reads from `ir/` (it validates `HandlerIR`/`WebsocketListenerIR` instances) but never writes to IR. It produces `context dicts` that the compiler consumes. It never imports from `compiler/` or `verifier/`.

#### Dispatch points

Recipes are dispatched at two points in the pipeline:

| Point | Where | What happens |
|-------|-------|-------------|
| `_apply_value_exprs()` | `builder.py:415` | Calls `recipe.output_value_expr(handler)` — stamps one expression onto every signal across every output_group |
| `build_template_context()` | `context_builder.py:19` | Calls `recipe.validate(handler_ir)` then `recipe.build_context(handler_ir)` — produces template context dict |

### `bmgen.compiler` — Deterministic Code Generator

**Purpose**: Generate Remotive Behavioral Model Python code from IR + recipe contexts using Jinja2 templates.

| Module | Responsibility |
|--------|---------------|
| `context_builder.py` | Take `BehavioralModelIR` + recipe contexts → build a single unified template context dict. Handles multi-output `output_groups` reconstruction and backward-compat flat fields. |
| `python_generator.py` | Load Jinja2 templates → render with context → write Python files to output directory. Pre-renders handler bodies and websocket bodies as strings, then injects them into `main.py.j2`. |

**Template responsibilities**:
- `main.py.j2`: Generates the complete behavioral model file (imports, dataclass/class definition, namespace setup, handler methods, websocket tasks, `main()` function, `__main__` entry point)
- `handler_direct.py.j2`: DirectSignalMapping + ThresholdMapping handler bodies (single + multi-output)
- `handler_toggle.py.j2`: ToggleButtonState handler bodies (single + multi-output)
- `handler_logic.py.j2`: Logic gate handler bodies (single + multi-output)
- `handler_blink.py.j2`: PeriodicBlinkingOutput handler body (single output only)
- `handler_websocket.py.j2`: Model-level websocket listener task
- `handler_reset.py.j2`: `on_reboot` handler that resets all owned states and calls `restbus.reset()`

**Template multi-output pattern** — three handler templates include an inline branch:

```jinja
{% if output_groups|length > 1 %}
  {# Multi-output: one restbus.update_signals() per group #}
  {% for group in output_groups %}
    await self.{{ group.namespace_var }}.restbus.update_signals(...)
  {% endfor %}
{% else %}
  {# Single-output: byte-identical to pre-multi-output rendering #}
  await self.{{ output_namespace_var }}.restbus.update_signals(...)
{% endif %}
```

This guarantees the single-output path produces literally identical Python code as before the multi-output refactor — verified by diff against the 5 child_detection ECUs.

**Boundary rule**: `compiler/` reads from `ir/` and `recipes/`. It writes to the filesystem (generated Python files). It never imports from `verifier/`.

### `bmgen.verifier` — 3-Layer Verification System

Same as before. Reads generated Python files (filesystem) and reads from `ir/` (for expected behavior specs). Never imports from `compiler/` or `recipes/`. Updated to read `handler_ir.output_groups` instead of the removed `output_signals`/`output_namespace` fields.

### `bmgen.cli` — Command Line Interface

| Command | Pipeline |
|---------|----------|
| `bmgen generate <yaml> --out <dir>` | YAML → IR → recipe validation → compiler → generated Python files |
| `bmgen verify <dir>` | Load generated dir → T1 → T2 → T3 → verification report JSON |
| `bmgen recipes` | List all available recipes |

## Boundary Summary

```text
YAML file
  │
  ▼
bmgen.ir.parser ──► raw spec dict
  │
  ▼
bmgen.ir.builder ──► BehavioralModelIR
  │                   1. _build_handlers (normalizes output → output_groups)
  │                   2. _build_websocket_listeners
  │                   3. _infer_namespaces (from handler/ws refs + namespace_types: map)
  │                   4. validate_namespace_types(spec, ir) — rules 14/15/16
  │                   5. validate(ir) — rules 1-13
  │                   6. _apply_value_exprs — recipe.output_value_expr() per handler
  ▼
bmgen.recipes.registry ──► recipe.validate(handler_ir) ──► context dicts
  │
  ▼
bmgen.compiler.context_builder ──► unified template context
  │   _merge_recipe_context: output_groups list + backward-compat flat fields
  ▼
bmgen.compiler.python_generator ──► Jinja2 templates ──► generated Python files
  │   handler templates: {% if output_groups|length > 1 %} branch per template
  ▼
bmgen.verifier.runner ──► T1 ──► T2 ──► T3 ──► VerificationReport JSON
```

**Key boundaries**:
- `ir/` is a **pure data layer**: no imports from compiler, recipes, or verifier
- `recipes/` is a **validation + context layer**: reads IR, produces dicts, no filesystem writes
- `compiler/` is a **generation layer**: reads IR + recipe contexts, writes filesystem
- `verifier/` is a **checking layer**: reads filesystem + IR, writes report, never generates code

## Design Decisions (service_oriented)

### Why `namespace_types:` is a flat map, not a list

A map (`name → type`) is naturally deduplicated by key. The old `namespaces:` list allowed duplicate names (caught only by Invariant 1 at validation time). A map also makes the "strict-required" rule (14) trivial: `name in type_map` is O(1). Finally, a map communicates intent: "these are the namespace types I have" — the role and restbus are derived, not declared.

### Why role inference instead of explicit role

Role was always derivable: if a handler reads from a namespace, it's an input; if it writes to it, it's an output; if both, it's both. The old schema forced users to state the obvious and then the validator checked they got it right. Inference eliminates a class of YAML authoring errors (mismatched role declarations) and cuts the namespace declaration from 4-6 lines to 1.

### Why `output_groups` instead of flat `output_signals`

The old IR had `output_namespace: str` + `output_signals: list[OutputSignalIR]`. A handler could only publish to one CAN bus. The new `output_groups: list[OutputGroupIR]` lets one handler fan out to N buses — each group is `(namespace, signals)`. The recipe's `output_value_expr()` still returns one expression; it's stamped onto every signal across every group. Generated code emits one `restbus.update_signals()` call per group.

### Why the template inline-branch pattern

The `{% if output_groups|length > 1 %}` branch in 3 handler templates means single-output handlers generate literally identical Python to the pre-refactor code. This was verified by diffing all 5 child_detection ECU outputs before and after migration — 4 of 5 are byte-identical, the 5th (central_hpc) differs only in hand-filled `novel_logic` stubs.

### Why `validate_namespace_types()` is called separately from `validate()`

The namespace_types rules (14/15/16) need the **raw spec dict** (to read `namespace_types:` and check for the deprecated `namespaces:` block). `validate(ir)` only receives the built IR. The builder calls `validate_namespace_types(spec, ir)` first, then `validate(ir)` — combining violations from both before deciding to raise.

## Child detection — runtime alignment (2026-07-06)

**Observed** layout tying compiler output to Remotive topology E2E:

```text
vehicle_functions/child_detection/
├── inc_schema/              # ecu + software_components (SWC YAML fragments)
│   ├── centralHPC.yaml
│   └── SWC_CAD_logic.yaml   # WeightedLogOdds: weights, threshold, multi-namespace input
├── generated/             # bmgen output (5 Python packages)
├── regen-all-from-inc-schema.sh
├── sync-generated-to-test_env.sh
└── topology/              # E2E harness (getting_started pattern)

test_env/VF_child-detection/
├── models/*/python/         # Docker images (sync from generated/)
├── tests/test_child_detection.py  # K-map expected vs HmiChildWarning actual
├── run-e2e-tests.sh
└── run-dashboard-interactive.sh   # http://localhost:8080 + one pytest per Enter
```

**bmgen unit tests**: `pytest tests/` in `remotive-bm-compiler/` — **139 passed** (2026-07-06).
