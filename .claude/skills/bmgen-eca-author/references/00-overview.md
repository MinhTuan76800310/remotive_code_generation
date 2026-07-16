# bmgen_ECA authoring — overview

## What this skill produces

A **schema_v2** ECU YAML file that `bmgen-eca parse` accepts (zero `E_*`).

Optional later: `bmgen-eca generate <yaml> --out <dir>` → `bmgen_generated/<ecu_snake>/{__init__.py,__main__.py}`.

## Mental model

```text
YAML text
  → parse/symbols/rules/semantic  (compiler)
  → green IR  OR  list of E_* / W_*
  → (only if green) codegen
```

Claude's job: write YAML that is green. Compiler is the source of truth.

## Provide then consume

1. Declare **providers**: can_rx, can_tx, parameters, state, timers
2. Write **rules** that only reference declared providers
3. Expressions use prefixes: `$state.x`, `$para.x`, `$[Bus]Frame.Signal`

Bare `$name` is always wrong in schema_v2.

## Read order (mandatory)

1. `03-field-graph.md`
2. `01-file-structure.md` + `02-subdomains.md`
3. `04-expr-surface.md` + `05-value-domains.md`
4. `06-yaml-to-generated.md` if user asks about runtime/codegen
5. `07-errors-fix.md` when parse fails
6. `examples/door_ecu.min.yaml` last (template, not sole memory)

## Hard gate

Task is **not done** while `bmgen-eca parse <file>` reports any error severity (`E_*`).
Warnings (`W_*`) are OK.

## Out of scope

- Recipe dialect under `remotive-bm-compiler/`
- Multi-bus ECUs
- SOME/IP codegen
- Marketplace plugin packaging
