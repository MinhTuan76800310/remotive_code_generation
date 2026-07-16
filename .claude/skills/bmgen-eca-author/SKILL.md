---
name: bmgen-eca-author
description: >-
  Author or fix schema_v2 ECU YAML for bmgen_ECA from natural language.
  Use when the user asks to write/generate/create an ECU mock YAML, ECA
  behavior YAML, door/seat/light ECU schema_v2, bmgen-eca input, or to
  fix bmgen-eca parse/generate errors (E_BARE_IDENT, E_UNRESOLVED_IDENT,
  E_TRIGGER_TARGET, etc.). Also use for /bmgen-eca-yaml.
---

# bmgen-eca-author

Compile-target dialect: **schema_v2** only (`apiVersion` + `ecu_mock.name` + `behavior`).
Mechanical truth: **`bmgen-eca parse`**.

## Before writing any YAML

Read references in this order (paths relative to this skill):

1. `references/03-field-graph.md`
2. `references/01-file-structure.md`
3. `references/02-subdomains.md`
4. `references/04-expr-surface.md`
5. `references/05-value-domains.md`
6. `references/examples/door_ecu.min.yaml` (template last)
7. On failure: `references/07-errors-fix.md`
8. If user asks about generated code: `references/06-yaml-to-generated.md`

## Workflow

1. Extract from NL: ECU name, RX/TX signals, parameters, state, timers, rules.
2. If exact `[Bus]Frame.Signal` ids are unknown → **ask the user**. Do not invent production bus names.
3. Write YAML **providers first**, then rules (see field graph).
4. Save to the path the user gave, or a sensible path under `workspace/` / project.
5. Run:

```bash
bmgen-eca parse <file>
```

6. If any `E_*` (error severity):
   - Open `references/07-errors-fix.md`
   - Patch YAML
   - Re-parse
   - Repeat until zero errors
7. `W_*` warnings are OK — report them, still DONE.
8. **Do not claim DONE** while errors remain.
9. Run `bmgen-eca generate` / `verify` **only if the user asks**.

## Hard rules

- Never use bare `$name` — always `$state` / `$para` / `$[Bus]…`
- Never use functions other than `min` / `max` / `abs`
- Never invent second bus in one ECU (MVP)
- Never teach or emit recipe-style remotive-bm-compiler YAML
- Signal strings in triggers/tx/expr must match interface declarations **exactly**

## DONE definition

`bmgen-eca parse <file>` exits 0 with **zero** error-severity diagnostics.
