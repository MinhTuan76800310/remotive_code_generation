# bmgen_ECA Claude Authoring (schema_v2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Project-local Claude Code skill + slash command + PostToolUse parse gate so NL → schema_v2 ECU YAML is written correctly and cannot be marked done while `bmgen-eca parse` still reports `E_*`.

**Architecture:** Teaching layer lives under `.claude/skills/bmgen-eca-author/` (SKILL.md + graph-first reference atlas). User entry is `/bmgen-eca-yaml`. Mechanical truth is existing `bmgen-eca parse`. A project hook after Write/Edit on ECA paths re-runs parse and feeds diagnostics back (exit 2) so the model is forced to fix. Phase 1 stops at parse green; `generate` only if the user asks.

**Tech Stack:** Claude Code skills/commands/hooks; bash + python3 for hook stdin JSON; existing `bmgen-eca` CLI (`pip install -e bmgen_ECA`).

**Spec of record:** [`docs/superpowers/specs/2026-07-16-bmgen-eca-claude-authoring-design.md`](../specs/2026-07-16-bmgen-eca-claude-authoring-design.md)

## Global Constraints

- **Project-local only** — all deliverables under `.claude/` in this repo; no marketplace plugin package.
- **Dialect = schema_v2 only** — `apiVersion` + `ecu_mock.name` + `behavior`; never teach recipe `remotive-bm-compiler` YAML.
- **Hard gate** — any `E_*` from `bmgen-eca parse` means task not DONE; `W_*` allowed.
- **Do not invent fields** — every field/value/error in references must match compiler (`parser.py`, `signals.py`, `diagnostics.py`, `DESIGN_DECISIONS.md`) or fixture.
- **Authoring order** — providers (interfaces/parameters/state/timers) before rules; graph before golden template.
- **Signal IDs** — if user did not supply bus/frame/signal, skill must ASK; no silent production bus names.
- **Hook exclude** — never parse `remotive-bm-compiler/**` or non-ECA YAML.
- **No compiler code changes** in this plan unless a doc bug is found (then fix doc, not dialect).
- **Working directory** — all paths relative to `/home/minhtuan958/Desktop/tuan_dz/code_generation/`.

## File map

| Path | Responsibility |
|------|----------------|
| `.claude/skills/bmgen-eca-author/SKILL.md` | Trigger + workflow + hard gate + read order |
| `.claude/skills/bmgen-eca-author/references/00-overview.md` | Mental model, when to use |
| `.claude/skills/bmgen-eca-author/references/01-file-structure.md` | Root shape |
| `.claude/skills/bmgen-eca-author/references/02-subdomains.md` | interfaces/parameters/state/timers/rules structs |
| `.claude/skills/bmgen-eca-author/references/03-field-graph.md` | Provide/consume graph (core) |
| `.claude/skills/bmgen-eca-author/references/04-expr-surface.md` | Expr forms + ops |
| `.claude/skills/bmgen-eca-author/references/05-value-domains.md` | Allowed values per attribute |
| `.claude/skills/bmgen-eca-author/references/06-yaml-to-generated.md` | YAML → BM package map |
| `.claude/skills/bmgen-eca-author/references/07-errors-fix.md` | E_* → YAML fix |
| `.claude/skills/bmgen-eca-author/references/examples/door_ecu.min.yaml` | Golden excerpt |
| `.claude/commands/bmgen-eca-yaml.md` | `/bmgen-eca-yaml` user entry |
| `.claude/hooks/bmgen-eca-parse-gate.sh` | PostToolUse parse gate script |
| `.claude/settings.json` | Add `hooks.PostToolUse` + allow `bmgen-eca` |

## Prerequisite (once per machine)

```bash
pip install -e bmgen_ECA
bmgen-eca parse bmgen_ECA/tests/fixtures/schema_v2.yaml
# Expected: exit 0; stderr ends with "ok: … warnings" or similar green footer
```

---

### Task 1: Reference atlas (graph-first docs + golden example)

**Files:**
- Create: `.claude/skills/bmgen-eca-author/references/00-overview.md`
- Create: `.claude/skills/bmgen-eca-author/references/01-file-structure.md`
- Create: `.claude/skills/bmgen-eca-author/references/02-subdomains.md`
- Create: `.claude/skills/bmgen-eca-author/references/03-field-graph.md`
- Create: `.claude/skills/bmgen-eca-author/references/04-expr-surface.md`
- Create: `.claude/skills/bmgen-eca-author/references/05-value-domains.md`
- Create: `.claude/skills/bmgen-eca-author/references/06-yaml-to-generated.md`
- Create: `.claude/skills/bmgen-eca-author/references/07-errors-fix.md`
- Create: `.claude/skills/bmgen-eca-author/references/examples/door_ecu.min.yaml`

**Interfaces:**
- Consumes: compiler contract from `bmgen_ECA` + design spec §3
- Produces: reference set that Task 2 `SKILL.md` will force-read in order `03 → 01+02 → 04+05 → (06) → (07) → example`

- [ ] **Step 1: Create directory tree**

```bash
mkdir -p .claude/skills/bmgen-eca-author/references/examples
```

- [ ] **Step 2: Write `00-overview.md`**

```markdown
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
```

- [ ] **Step 3: Write `01-file-structure.md`**

```markdown
# File structure (root)

## Required shape

```yaml
apiVersion: v1.0
ecu_mock:
  name: DoorECU          # required — class, package dir, SenderFilter
behavior:
  interfaces: { … }
  parameters: [ … ]
  state: [ … ]
  timers: [ … ]
  rules: [ … ]
```

## Field table

| Field | Required | Why |
|-------|----------|-----|
| `apiVersion` | yes | dialect pin (fixture uses `v1.0`) |
| `ecu_mock.name` | yes | only name source; missing → `E_MISSING_ECU_NAME` |
| `behavior` | yes | all semantics; missing → `E_PARSE` |
| `behavior.interfaces` | recommended | empty I/O → useless rules |
| `behavior.parameters` | optional | only if rules need `$para.*` |
| `behavior.state` | optional | only if rules need `$state.*` / set_state |
| `behavior.timers` | optional | only if `on_timer` rules exist |
| `behavior.rules` | optional at parse | skill should warn if empty ("no behavior") |
| `interfaces.someip_tx` non-empty | allowed | `W_SOMEIP_IGNORED`; no codegen |

## Naming

- `ecu_mock.name`: PascalCase convention (`DoorECU`)
- Generated package dir: snake_case (`door_ecu`)
- Class name: as written (`DoorECU`)
- No file-stem fallback — name comes only from YAML

## Related errors

`E_PARSE`, `E_MISSING_ECU_NAME`
```

- [ ] **Step 4: Write `02-subdomains.md`**

```markdown
# Subdomain structs

Each section: fields, provides, consumed by, example, related errors.

## interfaces

**Provides:** RX/TX signal ids (and optional someip list).

```yaml
interfaces:
  can_rx:
    - signal: "[DoorECU-BodyCan0]DoorCmd.TargetPosition"
  can_tx:
    - signal: "[DoorECU-BodyCan0]DoorStatus.CurrentPosition"
    - signal: "[DoorECU-BodyCan0]DoorStatus.IsMoving"
  someip_tx: []
```

| Field | Type | Notes |
|-------|------|-------|
| `can_rx[].signal` | string | full `[Bus]Frame.Signal` |
| `can_tx[].signal` | string | full `[Bus]Frame.Signal` |
| `someip_tx` | list | MVP ignored if non-empty → warn |

**Consumed by:** `on_rx.target`, `$[Bus]…` in expr (RX only), `tx.target` (TX only).

**Errors:** `E_BAD_SIGNAL_ID`, `E_MULTI_BUS_UNSUPPORTED`, `W_SOMEIP_IGNORED`

**MVP:** single bus only across all signals.

---

## parameters

**Provides:** `$para.<name>` constants.

```yaml
parameters:
  - name: min_pos
    type: float
    value: 0.0
```

| Field | Required | Domain |
|-------|----------|--------|
| `name` | yes | unique vs other param/state/timer names |
| `type` | yes | `bool` \| `int` \| `float` |
| `value` | yes | matches type |

**Consumed by:** condition/payload expr via `$para.name`.

**Errors:** `E_DUP_SYMBOL`, `W_UNUSED_PARAM`

---

## state

**Provides:** `$state.<name>` and `set_state` targets.

```yaml
state:
  - name: current_pos
    type: float
    init: 0.0
```

| Field | Required | Domain |
|-------|----------|--------|
| `name` | yes | unique |
| `type` | yes | `bool` \| `int` \| `float` |
| `init` | **yes** | matches type; missing → `E_MISSING_INIT` |

**Consumed by:** expr `$state.*`, `set_state.target`.

**Errors:** `E_MISSING_INIT`, `E_SET_STATE_UNKNOWN`, `E_DUP_SYMBOL`, `W_UNUSED_STATE`

---

## timers

**Provides:** `on_timer` targets.

```yaml
timers:
  - name: tick
    interval: 0.2
    auto_start: true
```

| Field | Required | Domain |
|-------|----------|--------|
| `name` | yes | unique |
| `interval` | yes | number **> 0** (seconds) |
| `auto_start` | yes | bool |

**Consumed by:** `trigger.type: on_timer` + `target: <name>`.

**Errors:** `E_BAD_TIMER_INTERVAL`, `E_TRIGGER_TARGET`, `E_DUP_SYMBOL`, `W_UNUSED_TIMER`

---

## rules

**Consumes:** providers above. Does not provide symbols.

```yaml
rules:
  - rule_id: receive_target
    trigger:
      type: on_rx
      target: "[DoorECU-BodyCan0]DoorCmd.TargetPosition"
    condition: "true"
    actions:
      - type: set_state
        target: target_pos
        payload: "max($para.min_pos, min($para.max_pos, $[DoorECU-BodyCan0]DoorCmd.TargetPosition))"
```

| Field | Required | Domain |
|-------|----------|--------|
| `rule_id` | yes | unique string |
| `trigger.type` | yes | `on_rx` \| `on_timer` |
| `trigger.target` | yes | RX raw signal **or** timer name |
| `condition` | yes | expr string (often `"true"`) |
| `actions` | yes | list of action objects |
| `actions[].type` | yes | `set_state` \| `tx` |
| `actions[].target` | yes | state name **or** TX raw signal |
| `actions[].payload` | yes | expr string |

**Order matters:** multiple rules on same frame/timer fire in **YAML source order**.

**Errors:** `E_BAD_TRIGGER_TYPE`, `E_TRIGGER_TARGET`, `E_BAD_ACTION`, `E_TX_TARGET_NOT_IN_CAN_TX`, `E_SET_STATE_UNKNOWN`, `E_BAD_EXPR`, `E_BARE_IDENT`, `E_UNRESOLVED_IDENT`, `E_UNKNOWN_FUNCTION`, `E_DUP_SYMBOL`
```

- [ ] **Step 5: Write `03-field-graph.md` (core)**

```markdown
# Field relationship graph (provide → consume)

Read this **before** copying any golden YAML.

## Graph

```mermaid
flowchart TB
  subgraph PROVIDERS
    RX["can_rx signal\n[Bus]Frame.Signal"]
    TX["can_tx signal\n[Bus]Frame.Signal"]
    P["parameters.name\n→ $para.x"]
    S["state.name\n→ $state.x + set_state"]
    T["timers.name\n→ on_timer target"]
  end

  subgraph RULE
    TR["trigger.type + target"]
    C["condition expr"]
    A1["action set_state"]
    A2["action tx"]
  end

  RX -->|on_rx.target exact raw string| TR
  T  -->|on_timer.target name| TR
  RX -->|expr $[Bus]Frame.Signal| C
  P  -->|expr $para.x| C
  S  -->|expr $state.x| C
  S  -->|set_state.target name| A1
  P  --> A1
  RX --> A1
  S  --> A1
  TX -->|tx.target exact raw string| A2
  S  --> A2
  P  --> A2
```

## Authoring checklist (order)

1. Choose `ecu_mock.name`
2. List every RX signal the ECU **reads** → `can_rx`
3. List every TX signal the ECU **writes** → `can_tx`
4. List parameters (`value`) and state (`init`) and timers
5. Only then write rules:
   - `on_rx.target` must equal a `can_rx` string **exactly**
   - `on_timer.target` must equal a timer `name`
   - `set_state.target` must equal a state `name`
   - `tx.target` must equal a `can_tx` string **exactly**
   - expr may only reference declared `$state` / `$para` / `$[rx]`

## Hard edges → errors

| If you… | You get |
|---------|---------|
| write `$speed` without prefix | `E_BARE_IDENT` |
| reference `$state.foo` never declared | `E_UNRESOLVED_IDENT` |
| `on_rx` target not in can_rx | `E_TRIGGER_TARGET` |
| `tx` target not in can_tx | `E_TX_TARGET_NOT_IN_CAN_TX` |
| `set_state` unknown name | `E_SET_STATE_UNKNOWN` |
| bad signal form | `E_BAD_SIGNAL_ID` |
| call `clamp(...)` | `E_UNKNOWN_FUNCTION` |
| use two different bus names | `E_MULTI_BUS_UNSUPPORTED` |

## MVP signal read rule

`$[Bus]Frame.Signal` in expr resolves to **can_rx only**. You cannot read a TX-only signal via `$[…]` unless it is also declared in `can_rx`.
```

- [ ] **Step 6: Write `04-expr-surface.md`**

```markdown
# Expression surface

## Allowed references

| Form | Resolves to |
|------|-------------|
| `$state.<name>` | STATE |
| `$para.<name>` | PARAM |
| `$[Bus]Frame.Signal` | can_rx entry (exact raw) |
| bare `$name` | **invalid** → `E_BARE_IDENT` |

## Operators

- Arithmetic: `+` `-` `*` `/`
- Unary: `-`
- Compare: `==` `!=` `>` `>=` `<` `<=`
- Boolean: `and` `or`
- Grouping: `( … )`
- Literals: numbers, `true` / `false`

## Functions (only)

| Call | Notes |
|------|-------|
| `min(a, b, …)` | ≥1 args; lowered with numpy in generated code |
| `max(a, b, …)` | same |
| `abs(x)` | one arg |

Anything else → `E_UNKNOWN_FUNCTION`.

## Forbidden (MVP)

- Strings in expr
- Arbitrary Python
- Reading TX-only signals via `$[…]`
- Mixed nonsense types (compiler may reject via `E_BAD_EXPR`)

## Examples

```text
true
abs($state.target_pos - $state.current_pos) > $para.pos_tolerance
max($para.min_pos, min($para.max_pos, $[DoorECU-BodyCan0]DoorCmd.TargetPosition))
$state.current_pos + max(0 - $para.move_step, min($para.move_step, $state.target_pos - $state.current_pos))
```
```

- [ ] **Step 7: Write `05-value-domains.md`**

```markdown
# Value domains (allowed attribute values)

| Attribute | Allowed | Error if wrong |
|-----------|---------|----------------|
| `apiVersion` | string (use `v1.0`) | shape/`E_PARSE` if root broken |
| `ecu_mock.name` | non-empty string | `E_MISSING_ECU_NAME` |
| signal id | `^\[([^\]]+)\]([^.]+)\.(.+)$` | `E_BAD_SIGNAL_ID` |
| param/state `type` | `bool` \| `int` \| `float` | parse/semantic issues |
| param `value` | matches type | |
| state `init` | matches type; **required** | `E_MISSING_INIT` |
| timer `interval` | number > 0 | `E_BAD_TIMER_INTERVAL` |
| timer `auto_start` | bool | |
| `trigger.type` | `on_rx` \| `on_timer` | `E_BAD_TRIGGER_TYPE` |
| `action.type` | `set_state` \| `tx` | `E_BAD_ACTION` |
| expr functions | `min` \| `max` \| `abs` | `E_UNKNOWN_FUNCTION` |
| buses in one ECU | **exactly one** distinct bus | `E_MULTI_BUS_UNSUPPORTED` |
| duplicate names | not allowed (param/state/timer/rule_id) | `E_DUP_SYMBOL` |

## Signal id anatomy

```text
[DoorECU-BodyCan0]DoorCmd.TargetPosition
 └────── bus ──────┘└frame┘└── signal ──┘
```

- Bus string becomes Remotive `CanNamespace` name in generated code.
- Frame groups handlers: one handler per `(bus, frame)`.
```

- [ ] **Step 8: Write `06-yaml-to-generated.md`**

```markdown
# YAML → generated Behavioral Model

Phase 1 skill stops at parse green. Read this when the user asks what runtime looks like or requests generate.

## Output layout

```text
{--out}/bmgen_generated/<snake_case(ecu_mock.name)>/
  __init__.py
  __main__.py
```

Example: `DoorECU` → `bmgen_generated/door_ecu/`.

## Mapping table

| YAML | Generated |
|------|-----------|
| `ecu_mock.name` | class name + package dir + `SenderFilter(ecu_name=…)` |
| unique signal bus | `CanNamespace("<bus>", …)` |
| RX/TX on same `(bus, frame)` | **one** `async def on_<Frame>(self, frame)` |
| `on_rx` rules same frame | sequential in handler, YAML order |
| `on_timer` rules same timer | one `while True: sleep(interval)` loop, YAML order |
| `parameters` | class attributes with `value` defaults |
| `state` + `init` | class attributes with `init` defaults |
| `timers` + `auto_start` | ticker tasks started when BM starts |
| `condition: "true"` | actions without `if` (always) |
| other condition | `if <lowered_python>:` |
| `set_state` | `self.<name> = <payload_py>` |
| `tx` | namespace signal write of lowered payload |
| `min`/`max`/`abs` | `np.minimum.reduce` / `np.maximum.reduce` / `np.abs` |

## Annotated DoorECU slice

YAML rule `receive_target` (on_rx DoorCmd.TargetPosition) becomes part of the **DoorCmd** frame handler: read `TargetPosition` from `frame.signals`, assign clamped value to `self.target_pos`.

YAML rules `move_door` + `publish_status` (both on_timer `tick`) share one ticker loop: first step position, then update `door_moving` and TX status — because that is YAML order.

## Generate command

```bash
bmgen-eca generate path/to/ecu.yaml --out .
# → ./bmgen_generated/<ecu_snake>/
bmgen-eca verify ./bmgen_generated/<ecu_snake>
```

Only run generate if the user asks. Parse green is enough for authoring DONE.
```

- [ ] **Step 9: Write `07-errors-fix.md`**

Build the table from live catalog (do not hand-copy stale codes):

```bash
bmgen-eca errors
```

Then write the file as:

```markdown
# Errors → fix (hard-gate checklist)

Source of truth: `bmgen-eca errors` (frozen `ERROR_CATALOG`).

When parse fails: for each `E_*` line, apply the fix below, then re-run parse.

| Code | When | YAML fix |
|------|------|----------|
| `E_PARSE` | YAML load / bad shape | Fix YAML syntax; ensure root mapping with `apiVersion`, `ecu_mock`, `behavior` |
| `E_MISSING_ECU_NAME` | missing `ecu_mock.name` | Set `ecu_mock.name: YourEcu` |
| `E_BAD_SIGNAL_ID` | signal not `[Bus]Frame.Signal` | Rewrite to `[Bus]Frame.Signal` |
| `E_DUP_SYMBOL` | duplicate param/state/timer/rule_id | Rename to unique |
| `E_BARE_IDENT` | `$name` without prefix | Use `$state.x` / `$para.x` / `$[Bus]Frame.Signal` |
| `E_UNRESOLVED_IDENT` | `$` ref not declared | Declare provider or remove ref |
| `E_UNKNOWN_FUNCTION` | call not min\|max\|abs | Replace with min/max/abs only |
| `E_TRIGGER_TARGET` | bad on_rx/on_timer target | Point at declared can_rx raw or timer name |
| `E_TX_TARGET_NOT_IN_CAN_TX` | tx target missing | Add to `interfaces.can_tx` or fix target string |
| `E_SET_STATE_UNKNOWN` | set_state target missing | Add to `state` or fix name |
| `E_BAD_EXPR` | expr outside MVP | See `04-expr-surface.md` |
| `E_BAD_ACTION` | action.type invalid | Use `tx` or `set_state` |
| `E_BAD_TRIGGER_TYPE` | trigger.type invalid | Use `on_rx` or `on_timer` |
| `E_MISSING_INIT` | state without init | Add `init:` |
| `E_BAD_TIMER_INTERVAL` | interval not positive number | Set float/int seconds > 0 |
| `E_MULTI_BUS_UNSUPPORTED` | >1 bus | Use one bus name for all signals |

## Warnings (do not block DONE)

| Code | Meaning | Action |
|------|---------|--------|
| `W_UNUSED_PARAM` | param never referenced | remove or keep as doc |
| `W_UNUSED_STATE` | state never used | remove or use |
| `W_UNUSED_TIMER` | timer never targeted | remove or add rule |
| `W_SOMEIP_IGNORED` | someip_tx non-empty | OK for MVP; no codegen |

## Loop

```text
parse → E_*? → fix using this table + 03-field-graph → parse again
until zero errors
```
```

- [ ] **Step 10: Write golden example `examples/door_ecu.min.yaml`**

Copy content from `bmgen_ECA/tests/fixtures/schema_v2.yaml` (keep comments). Do not invent a second dialect.

```bash
cp bmgen_ECA/tests/fixtures/schema_v2.yaml \
  .claude/skills/bmgen-eca-author/references/examples/door_ecu.min.yaml
```

- [ ] **Step 11: Sanity-check example still parses**

```bash
bmgen-eca parse .claude/skills/bmgen-eca-author/references/examples/door_ecu.min.yaml
```

Expected: exit code **0**.

- [ ] **Step 12: Commit**

```bash
git add .claude/skills/bmgen-eca-author/references
git commit -m "$(cat <<'EOF'
docs(claude): bmgen-eca authoring reference atlas

Graph-first schema_v2 field docs, value domains, error fix map,
and golden DoorECU example for NL→YAML skill.
EOF
)"
```

---

### Task 2: `SKILL.md` (workflow + hard gate)

**Files:**
- Create: `.claude/skills/bmgen-eca-author/SKILL.md`

**Interfaces:**
- Consumes: references from Task 1
- Produces: auto-invocable skill `bmgen-eca-author` for NL ECU YAML authoring

- [ ] **Step 1: Write `SKILL.md`**

```markdown
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
```

- [ ] **Step 2: Verify skill file is discoverable**

```bash
test -f .claude/skills/bmgen-eca-author/SKILL.md && echo OK_SKILL
# Optional: start a new Claude Code session later and confirm skill appears in available skills list
```

Expected: `OK_SKILL`

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/bmgen-eca-author/SKILL.md
git commit -m "$(cat <<'EOF'
feat(claude): bmgen-eca-author skill with parse hard gate

Forces graph-first reads and bmgen-eca parse loop until zero E_*.
EOF
)"
```

---

### Task 3: Slash command `/bmgen-eca-yaml`

**Files:**
- Create: `.claude/commands/bmgen-eca-yaml.md`

**Interfaces:**
- Consumes: same workflow as skill (user-invocable)
- Produces: `/bmgen-eca-yaml` command

- [ ] **Step 1: Write command file**

```markdown
---
description: Author schema_v2 ECU YAML from natural language; parse-hard-gate with bmgen-eca
argument-hint: "<NL description of ECU behavior> [--out path/to.yaml]"
---

# /bmgen-eca-yaml

User wants schema_v2 ECU YAML from: `$ARGUMENTS`

## Instructions

1. Invoke the same workflow as skill `bmgen-eca-author` (read its `SKILL.md` and references).
2. If `$ARGUMENTS` contains `--out <path>`, write the YAML there; otherwise choose a clear path and state it.
3. After write, run `bmgen-eca parse <path>`.
4. Fix all `E_*` until parse is green. Do not stop early.
5. Report: output path, warning summary, and that generate was **not** run unless user also asked.

Do not use recipe bmgen dialect. Do not invent bus/signal names without asking.
```

- [ ] **Step 2: Commit**

```bash
git add .claude/commands/bmgen-eca-yaml.md
git commit -m "$(cat <<'EOF'
feat(claude): add /bmgen-eca-yaml slash command

User-invocable NL→schema_v2 YAML with bmgen-eca parse hard gate.
EOF
)"
```

---

### Task 4: PostToolUse parse gate hook + permissions

**Files:**
- Create: `.claude/hooks/bmgen-eca-parse-gate.sh`
- Modify: `.claude/settings.json` (add `hooks` + allow `bmgen-eca`)

**Interfaces:**
- Consumes: Write/Edit tool input JSON on stdin (`tool_input.file_path`)
- Produces: exit 0 skip/success; exit 2 + stderr diagnostics for ECA parse failures

- [ ] **Step 1: Write hook script**

Create `.claude/hooks/bmgen-eca-parse-gate.sh`:

```bash
#!/usr/bin/env bash
# PostToolUse Write|Edit → bmgen-eca parse for schema_v2 ECA YAML only.
# Exit 0: skip or green. Exit 2: feed stderr back to Claude (errors remain).
set -euo pipefail

input=$(cat)

# Extract file path from Claude Code hook JSON
file_path=$(python3 -c '
import json,sys
raw=sys.stdin.read()
try:
    d=json.loads(raw)
except Exception:
    print(""); sys.exit(0)
# common shapes: tool_input.file_path or tool_input.path
ti=d.get("tool_input") or d.get("toolInput") or {}
p=ti.get("file_path") or ti.get("filePath") or ti.get("path") or ""
print(p)
' <<<"$input")

if [[ -z "${file_path}" ]]; then
  exit 0
fi

# Only YAML
case "${file_path}" in
  *.yaml|*.yml) ;;
  *) exit 0 ;;
esac

# Exclude recipe compiler tree and obvious non-ECA
case "${file_path}" in
  *remotive-bm-compiler*|*docker-compose*.yml|*docker-compose*.yaml|*/.github/*)
    exit 0 ;;
esac

# Include heuristics: known ECA locations OR content sniff
include=0
case "${file_path}" in
  *schema_v2.yaml|*bmgen_ECA/tests/fixtures/*|*workspace/*/schema/*|*/passenger_welcome_eca/*|*/bmgen-eca-author/references/examples/*)
    include=1 ;;
esac

if [[ "$include" -eq 0 && -f "$file_path" ]]; then
  if python3 -c '
import sys
p=sys.argv[1]
try:
    t=open(p,encoding="utf-8",errors="replace").read(4000)
except Exception:
    sys.exit(1)
sys.exit(0 if ("apiVersion:" in t and "ecu_mock:" in t and "behavior:" in t) else 1)
' "$file_path"; then
    include=1
  fi
fi

if [[ "$include" -eq 0 ]]; then
  exit 0
fi

if ! command -v bmgen-eca >/dev/null 2>&1; then
  echo "bmgen-eca-parse-gate: bmgen-eca not on PATH. Run: pip install -e bmgen_ECA" >&2
  exit 2
fi

set +e
out=$(bmgen-eca parse "$file_path" 2>&1)
rc=$?
set -e

if [[ $rc -ne 0 ]]; then
  echo "bmgen-eca-parse-gate: parse FAILED for $file_path" >&2
  echo "$out" >&2
  echo "bmgen-eca-parse-gate: fix all E_* (see skill references/07-errors-fix.md); task not DONE." >&2
  exit 2
fi

# green: keep transcript light
echo "bmgen-eca-parse-gate: ok $file_path"
echo "$out" | tail -n 1
exit 0
```

```bash
chmod +x .claude/hooks/bmgen-eca-parse-gate.sh
```

- [ ] **Step 2: Unit-smoke the hook offline (no Claude session)**

```bash
# A) non-yaml → skip
echo '{"tool_input":{"file_path":"README.md"}}' | .claude/hooks/bmgen-eca-parse-gate.sh
echo "A rc=$?"   # expect 0

# B) recipe path → skip
echo '{"tool_input":{"file_path":"remotive-bm-compiler/examples/bcm_direct.yaml"}}' | .claude/hooks/bmgen-eca-parse-gate.sh
echo "B rc=$?"   # expect 0

# C) golden fixture → green
echo '{"tool_input":{"file_path":"bmgen_ECA/tests/fixtures/schema_v2.yaml"}}' | .claude/hooks/bmgen-eca-parse-gate.sh
echo "C rc=$?"   # expect 0

# D) broken temp yaml → exit 2
python3 - <<'PY'
from pathlib import Path
p=Path("/tmp/bad_eca.yaml")
p.write_text("apiVersion: v1.0\necu_mock: {name: X}\nbehavior:\n  interfaces: {can_rx: [], can_tx: [], someip_tx: []}\n  parameters: []\n  state: []\n  timers: []\n  rules:\n    - rule_id: r\n      trigger: {type: on_rx, target: \"[B]F.S\"}\n      condition: \"$speed\"\n      actions: []\n")
print(p)
PY
echo '{"tool_input":{"file_path":"/tmp/bad_eca.yaml"}}' | .claude/hooks/bmgen-eca-parse-gate.sh
echo "D rc=$?"   # expect 2
```

Expected:
- A/B/C → `rc=0`
- D → `rc=2` and stderr contains an `E_` code (e.g. `E_BARE_IDENT` or `E_TRIGGER_TARGET`)

- [ ] **Step 3: Patch `.claude/settings.json`**

Read current file first. Merge **without removing** existing `permissions.allow` entries.

Add to `permissions.allow` (if missing):

```json
"Bash(bmgen-eca *)",
"Bash(python -m bmgen_eca *)",
"Bash(.claude/hooks/bmgen-eca-parse-gate.sh *)"
```

Add top-level `hooks` key (settings format with wrapper used by Claude Code project settings):

```json
"hooks": {
  "PostToolUse": [
    {
      "matcher": "Write|Edit",
      "hooks": [
        {
          "type": "command",
          "command": "bash \"${CLAUDE_PROJECT_DIR}/.claude/hooks/bmgen-eca-parse-gate.sh\"",
          "timeout": 60,
          "statusMessage": "bmgen-eca parse gate"
        }
      ]
    }
  ]
}
```

If the project's Claude Code version rejects `hooks` wrapper, try the alternate **direct** form from plugin-dev docs (events at top level). Prefer whatever `claude` validates; do not leave a broken settings.json.

Validate JSON:

```bash
python3 -m json.tool .claude/settings.json > /dev/null && echo OK_JSON
```

Expected: `OK_JSON`

- [ ] **Step 4: Commit**

```bash
git add .claude/hooks/bmgen-eca-parse-gate.sh .claude/settings.json
git commit -m "$(cat <<'EOF'
feat(claude): PostToolUse bmgen-eca parse gate for ECA YAML

Hook runs bmgen-eca parse after Write/Edit on schema_v2 paths;
exit 2 surfaces E_* so authoring cannot silently finish red.
EOF
)"
```

---

### Task 5: Acceptance (manual + scripted checks)

**Files:**
- Create: `.claude/skills/bmgen-eca-author/ACCEPTANCE.md` (short checklist only)

**Interfaces:**
- Consumes: Tasks 1–4 deliverables
- Produces: evidence that S1–S5 / T1–T6 from the design spec are met or blocked with reason

- [ ] **Step 1: Write `ACCEPTANCE.md`**

```markdown
# Acceptance checklist — bmgen-eca-author

- [ ] T1: Skill file exists; description mentions schema_v2 / bmgen-eca / E_* 
- [ ] T2: `bmgen-eca parse` green on references/examples/door_ecu.min.yaml
- [ ] T3: Hook exit 2 on deliberate bad YAML with E_* in stderr
- [ ] T4: Hook exit 0 on remotive-bm-compiler/examples/bcm_direct.yaml (skip)
- [ ] T5: references include 03 graph, 02 five subdomains, 05 domains, 06 map, 07 errors
- [ ] T6: no marketplace plugin package; all under .claude/
- [ ] S5: SKILL.md says generate is optional / not required for DONE
```

- [ ] **Step 2: Run scripted acceptance**

```bash
set -e
test -f .claude/skills/bmgen-eca-author/SKILL.md
test -f .claude/commands/bmgen-eca-yaml.md
test -x .claude/hooks/bmgen-eca-parse-gate.sh
for f in 00-overview 01-file-structure 02-subdomains 03-field-graph 04-expr-surface 05-value-domains 06-yaml-to-generated 07-errors-fix; do
  test -f ".claude/skills/bmgen-eca-author/references/$f.md"
done
bmgen-eca parse .claude/skills/bmgen-eca-author/references/examples/door_ecu.min.yaml

echo '{"tool_input":{"file_path":"remotive-bm-compiler/examples/bcm_direct.yaml"}}' | .claude/hooks/bmgen-eca-parse-gate.sh
test $? -eq 0

python3 - <<'PY'
from pathlib import Path
p=Path('/tmp/accept_bad_eca.yaml')
p.write_text('''apiVersion: v1.0
ecu_mock: {name: Bad}
behavior:
  interfaces: {can_rx: [{signal: "[B]F.S"}], can_tx: [], someip_tx: []}
  parameters: []
  state: []
  timers: []
  rules:
    - rule_id: r
      trigger: {type: on_rx, target: "[B]F.S"}
      condition: "$speed"
      actions: []
''')
print(p)
PY
set +e
echo '{"tool_input":{"file_path":"/tmp/accept_bad_eca.yaml"}}' | .claude/hooks/bmgen-eca-parse-gate.sh
rc=$?
set -e
test $rc -eq 2

python3 -m json.tool .claude/settings.json > /dev/null
grep -q 'bmgen-eca-parse-gate' .claude/settings.json
grep -q 'bmgen-eca-author' .claude/skills/bmgen-eca-author/SKILL.md
echo ACCEPTANCE_SCRIPTED_OK
```

Expected final line: `ACCEPTANCE_SCRIPTED_OK`

- [ ] **Step 3: Manual NL smoke (human or this session)**

Prompt (in a Claude Code session with the new skill loaded):

> Viết ECU YAML schema_v2 cho cửa trượt: nhận TargetPosition, clamp min/max, mỗi 0.2s bước current_pos, publish CurrentPosition + IsMoving. Bus/signal dùng đúng fixture DoorECU.

Expect:
1. Skill engages (or user runs `/bmgen-eca-yaml …`)
2. YAML written
3. `bmgen-eca parse` green (hook and/or skill)
4. No claim of DONE while red

- [ ] **Step 4: Tick ACCEPTANCE.md + commit**

```bash
git add .claude/skills/bmgen-eca-author/ACCEPTANCE.md
git commit -m "$(cat <<'EOF'
test(claude): acceptance checklist for bmgen-eca authoring skill

Scripted hook/parse gates plus manual NL smoke checklist.
EOF
)"
```

---

## Spec coverage (self-review)

| Spec requirement | Task |
|------------------|------|
| S1 skill auto-load / NL authoring | Task 2 description + Task 3 command |
| S2 Write/Edit → parse hard gate | Task 2 workflow + Task 4 hook |
| S3 atlas: tree, structs, graph, domains, yaml→gen, errors | Task 1 |
| S4 project-local only | all tasks under `.claude/` |
| S5 parse green enough; generate optional | Task 2 hard rules + `06` + ACCEPTANCE |
| Hook path include/exclude | Task 4 script |
| Permissions for bmgen-eca | Task 4 settings |
| Signal ask-if-unknown | Task 2 workflow step 2 |
| T1–T6 acceptance | Task 5 |

## Placeholder scan

No TBD/TODO steps; file bodies inlined; commands exact; expected exit codes stated.

## Type/name consistency

- Skill name: `bmgen-eca-author` (folder + frontmatter `name`)
- Command: `bmgen-eca-yaml` → `/bmgen-eca-yaml`
- Hook script: `.claude/hooks/bmgen-eca-parse-gate.sh`
- CLI: `bmgen-eca parse|generate|verify|errors`

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-16-bmgen-eca-claude-authoring.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session with executing-plans + checkpoints  

Which approach?
