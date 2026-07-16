# Design: Claude Code authoring for bmgen_ECA (schema_v2 YAML)

**Date:** 2026-07-16  
**Status:** Approved for implementation planning  
**Branch context:** `service_oriented`  
**Compiler:** `bmgen_ECA` (`bmgen-eca` CLI)  
**Dialect:** schema_v2 (`apiVersion` + `ecu_mock.name` + `behavior`)

---

## 1. Goal & success bar

### Goal

In this monorepo only, Claude (and the user via slash command) can author **schema_v2 ECU YAML** from natural language such that:

1. Structure, fields, and value domains match the dialect (no guessing).
2. After Write/Edit of an ECA YAML file, **`bmgen-eca parse` is green** — hard gate: any `E_*` means not done; `W_*` is allowed.
3. Claude understands **field relationships** (provide/consume), **subdomain structs**, **allowed attribute values**, and **how YAML maps to generated Remotive BM** — not only a copy of the DoorECU golden file.

### Success criteria

| ID | Criterion |
|----|-----------|
| S1 | Prompt like “viết ECU cửa bước từng nấc…” auto-loads the authoring skill and produces schema_v2-shaped YAML. |
| S2 | Write/Edit of an ECA path runs `bmgen-eca parse`; remaining `E_*` blocks “done”. |
| S3 | Reference docs include: file tree, subdomain structs, **field relationship graph**, value domains, YAML→generated map, error→fix map. |
| S4 | Project-local only under `.claude/`; no marketplace plugin required. |
| S5 | Phase 1 stop condition is **parse green**. `generate` is optional when the user asks. |

### Non-goals (phase 1)

- Installable marketplace / plugin package
- MCP server wrapping `bmgen-eca`
- Multi-ECU topology authoring
- Teaching legacy recipe dialect (`remotive-bm-compiler` / WeightedLogOdds etc.)
- Live Remotive bus E2E as part of the skill

### Locked product choices (from brainstorm)

| Decision | Choice |
|----------|--------|
| Success bar for “Claude knows how to write YAML” | **B** — Skill + validate loop (`bmgen-eca parse`) |
| Install scope | **A** — Project-local only |
| Validate loop stop | **A** — Hard gate on `E_*` |
| Architecture approach | **2** — Skill + slash command + PostToolUse parse gate |
| Teaching style | Atlas references with **relationship graph first** |

---

## 2. Architecture

### Layout

```text
.claude/
  skills/
    bmgen-eca-author/
      SKILL.md
      references/
        00-overview.md
        01-file-structure.md
        02-subdomains.md
        03-field-graph.md          # core — provide/consume
        04-expr-surface.md
        05-value-domains.md
        06-yaml-to-generated.md
        07-errors-fix.md
        examples/
          door_ecu.min.yaml        # golden excerpt or pointer to fixture
  commands/
    bmgen-eca-yaml.md              # /bmgen-eca-yaml <NL>
  settings.json                    # + PostToolUse hook + Bash allow for bmgen-eca
```

### Responsibility split

| Piece | Does | Does not |
|-------|------|----------|
| `SKILL.md` | Trigger on NL ECU authoring; force reference read order; write YAML; run parse; loop on `E_*` | Invent dialect; skip parse |
| `references/*` | Source of truth for how to write | Run tools |
| `/bmgen-eca-yaml` | User-invocable same workflow | Replace auto skill invoke |
| PostToolUse hook | After Write/Edit on ECA paths → `bmgen-eca parse <file>`; surface diags | Fix YAML; touch non-ECA YAML |
| `bmgen-eca` CLI | Mechanical truth (existing) | Teach NL |

### Hook path policy

**Include (examples):**

- `**/schema_v2.yaml`
- `workspace/**/schema/**/*.yaml`
- `bmgen_ECA/tests/fixtures/**/*.yaml`
- Optional content sniff: root has both `apiVersion:` and `ecu_mock:`

**Exclude:**

- `remotive-bm-compiler/**`
- recipe-style examples, `docker-compose.yml`, non-ECA config YAML

If `bmgen-eca` is missing: hook message must say `pip install -e bmgen_ECA` — never fake green.

### Skill forced read order

1. `03-field-graph.md` (relationships first)
2. `01-file-structure.md` + `02-subdomains.md`
3. `04-expr-surface.md` + `05-value-domains.md`
4. `06-yaml-to-generated.md` when user cares about runtime/codegen
5. `07-errors-fix.md` on parse failure
6. Golden example last (template, not sole memory)

### Data flow

```text
User NL
  → skill loads graph + structs + domains
  → draft YAML (providers first, rules last)
  → Write file
  → hook and/or skill: bmgen-eca parse
       ├─ E_*  → fix via 07-errors-fix + graph → re-parse
       └─ green (W_* ok) → DONE
  → [optional] bmgen-eca generate --out … if user asks
```

### Permissions

Project `.claude/settings.json` must allow:

- `Bash(bmgen-eca *)` and/or `Bash(python -m bmgen_eca *)`

so parse does not stall on permission prompts.

---

## 3. Reference content (authoring atlas)

All field names and constraints below are **Observed** from `bmgen_ECA` sources and fixtures:

- `bmgen_ECA/tests/fixtures/schema_v2.yaml`
- `bmgen_ECA/src/bmgen_eca/parser.py`
- `bmgen_ECA/src/bmgen_eca/signals.py`
- `bmgen_ECA/src/bmgen_eca/diagnostics.py`
- `bmgen_ECA/DESIGN_DECISIONS.md` (§1–§3 provide/consume, IR)

Do not invent fields not enforced by the compiler.

### 3.1 Root file structure (`01-file-structure.md`)

```yaml
apiVersion: v1.0
ecu_mock:
  name: DoorECU
behavior:
  interfaces: …
  parameters: …
  state: …
  timers: …
  rules: …
```

| Field | Required | Why |
|-------|----------|-----|
| `apiVersion` | yes | dialect pin |
| `ecu_mock.name` | yes | only name source → class, package dir, `SenderFilter` (no file-stem fallback) |
| `behavior` | yes | all semantics |
| empty `rules` | parse may allow | skill should warn “no behavior” |
| non-empty `someip_tx` | allowed | `W_SOMEIP_IGNORED`; no codegen |

### 3.2 Subdomain structs (`02-subdomains.md`)

**interfaces**

```yaml
interfaces:
  can_rx:  [{ signal: "[Bus]Frame.Signal" }, …]
  can_tx:  [{ signal: "[Bus]Frame.Signal" }, …]
  someip_tx: []
```

**parameters**

```yaml
- name: min_pos       # unique among param/state/timer names
  type: float         # MVP: bool | int | float
  value: 0.0          # compile-time constant → $para.min_pos
```

**state**

```yaml
- name: current_pos
  type: float
  init: 0.0           # required → E_MISSING_INIT
```

**timers**

```yaml
- name: tick
  interval: 0.2       # seconds, number > 0
  auto_start: true
```

**rules**

```yaml
- rule_id: receive_target
  trigger:
    type: on_rx | on_timer
    target: "<rx signal raw>" | "<timer name>"
  condition: "<expr>"
  actions:
    - type: set_state | tx
      target: <state name> | <tx signal raw>
      payload: "<expr>"
```

Each subdomain page in the skill must answer: *what / required fields / allowed values / who provides / who consumes / example / related errors*.

### 3.3 Field relationship graph (`03-field-graph.md`) — core

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

  RX -->|on_rx.target exact raw| TR
  T  -->|on_timer.target name| TR
  RX -->|expr $[Bus]Frame.Signal read| C
  P  -->|expr $para.x| C
  S  -->|expr $state.x| C
  P  --> A1
  S  -->|set_state.target name| A1
  S  -->|payload may read $state| A1
  RX --> A1
  TX -->|tx.target exact raw| A2
  S  -->|payload often $state| A2
  P  --> A2
```

**Authoring order (skill enforces)**

1. `ecu_mock.name`
2. All RX/TX signals used
3. parameters + state (+ init) + timers
4. rules (every target already exists)
5. expr only with `$state.*` / `$para.*` / `$[Bus]…` + min/max/abs

**Hard edges (compiler)**

| Edge broken | Error |
|-------------|-------|
| bare `$name` | `E_BARE_IDENT` |
| `$…` not declared | `E_UNRESOLVED_IDENT` |
| `on_rx` target ∉ can_rx | `E_TRIGGER_TARGET` |
| `tx` target ∉ can_tx | `E_TX_TARGET_NOT_IN_CAN_TX` |
| `set_state` target ∉ state | `E_SET_STATE_UNKNOWN` |
| signal not `[Bus]Frame.Signal` | `E_BAD_SIGNAL_ID` |
| call outside min/max/abs | `E_UNKNOWN_FUNCTION` |
| >1 bus in interfaces | `E_MULTI_BUS_UNSUPPORTED` |
| unknown trigger type | `E_BAD_TRIGGER_TYPE` |
| unknown action type | `E_BAD_ACTION` |
| state missing init | `E_MISSING_INIT` |
| bad timer interval | `E_BAD_TIMER_INTERVAL` |
| duplicate names | `E_DUP_SYMBOL` |

Provide/consume model (Observed from DESIGN_DECISIONS):

```text
PROVIDERS:
  can_rx[signal]   → RX
  can_tx[signal]   → TX
  parameters[name] → PARAM
  state[name]      → STATE
  timers[name]     → TIMER

CONSUMERS:
  trigger.target (on_rx → RX raw | on_timer → TIMER name)
  $state.<name> / $para.<name> / $[Bus]Frame.Signal (RX read only in MVP)
  set_state.target → STATE
  tx.target → TX
```

### 3.4 Expr surface (`04-expr-surface.md`)

| Form | Lookup |
|------|--------|
| `$state.<name>` | STATE |
| `$para.<name>` | PARAM |
| `$[Bus]Frame.Signal` | can_rx only (MVP) |
| bare `$name` | invalid |

Ops: `+ - * /`, compare (`== != > >= < <=`), `and`/`or`, unary `-`, parens.  
Calls: `min`, `max`, `abs` only.  
No strings in expr (MVP).  
Lowering (for awareness): `min`/`max` → `np.minimum.reduce` / `np.maximum.reduce`; `abs` → `np.abs`.

### 3.5 Value domains (`05-value-domains.md`)

| Attribute | Allowed | Notes |
|-----------|---------|-------|
| `apiVersion` | string (fixture `v1.0`) | required pin |
| `ecu_mock.name` | non-empty; PascalCase convention | → snake package dir |
| signal id | `^\[([^\]]+)\]([^.]+)\.(.+)$` | bus = CanNamespace name |
| param/state `type` | `bool` \| `int` \| `float` | MVP |
| `value` / `init` | match type | state must have `init` |
| `interval` | number > 0 | seconds |
| `auto_start` | bool | |
| `trigger.type` | `on_rx` \| `on_timer` | |
| `action.type` | `set_state` \| `tx` | |
| expr functions | `min` \| `max` \| `abs` | |
| multi-bus | forbidden MVP | |

### 3.6 YAML → generated (`06-yaml-to-generated.md`)

| YAML | Generated |
|------|-----------|
| `ecu_mock.name: DoorECU` | `bmgen_generated/door_ecu/`, `class DoorECU` |
| unique `SignalId.bus` | `CanNamespace("<bus>", …)` |
| can_rx/tx same `(bus, frame)` | **one** handler per frame |
| multiple `on_rx` same frame | YAML source order, fire-all |
| multiple `on_timer` same timer | one ticker loop, YAML order |
| parameters | instance attrs from `value` |
| state + init | instance attrs |
| timers + auto_start | start on BM start if true |
| set_state / tx / condition | lowered Python |

Output files only: `__init__.py` + `__main__.py` (no `log.py`).

Reference shows **one annotated DoorECU slice** ↔ matching handler/ticker fragment — not a second compiler.

### 3.7 Errors → fix (`07-errors-fix.md`)

Table derived from frozen `ERROR_CATALOG` in `diagnostics.py`: code → when → exact YAML edit. Skill hard-gate loop uses this checklist.

### 3.8 NL extraction rules

| From NL alone | Must ask user if missing |
|---------------|--------------------------|
| rule logic sketch, state/param names | exact bus/frame/signal strings if no topology/DBC |
| timer intervals if user stated timing | real signal map from vehicle project |
| clamp/step patterns | multi-ECU coordination (out of phase 1) |

If signal IDs unknown → **ask** or use clearly marked placeholders. Silent invented production bus names are forbidden.

---

## 4. Workflow, hard gate, hook

### Skill workflow

1. Load refs in order: graph → structure → subdomains → expr → domains  
2. Extract from NL: ECU name, I/O, params, state, timers, rules  
3. If signal IDs / bus unknown → ASK  
4. Write YAML: providers first, rules last  
5. `bmgen-eca parse <file>`  
6. Any `E_*` → fix via `07-errors-fix` + graph → re-parse  
7. Green (`W_*` ok) → report path + warnings → **DONE**  
8. Optional: `bmgen-eca generate --out …` only if user asks  

**DONE definition:** parse exit 0 with zero error-severity diagnostics. Skill text must say: do not claim complete while `E_*` remain.

### Slash command `/bmgen-eca-yaml`

Free-text NL (+ optional output path). Same workflow as skill; user-invocable when model does not auto-trigger.

### Hook (PostToolUse Write | Edit)

| | |
|--|--|
| When | path matches ECA allowlist |
| Run | `bmgen-eca parse <written-path>` |
| Fail | full diagnostic text in tool result |
| Success | quiet or `ok: N warnings` |
| Missing CLI | install hint; not green |

Skill is primary teacher + loop; hook is safety net. Both are in scope for phase 1.

---

## 5. Testing & acceptance

| ID | Check | How |
|----|-------|-----|
| T1 | Skill triggers on ECU YAML authoring prompts | description keywords + manual |
| T2 | NL → DoorECU-like YAML → parse green | one E2E after implement |
| T3 | Bad YAML (bare `$x`) → diags → fix → green | red path |
| T4 | Write recipe example under `remotive-bm-compiler/` → hook does not run | exclusion |
| T5 | Refs contain graph + 5 subdomain structs + value table + yaml→gen + error map | file review |
| T6 | All under `.claude/`; no marketplace | tree |

---

## 6. Implementation notes (for writing-plans)

Suggested build order (not a full plan):

1. Reference atlas (`03` graph first, then 01/02/04/05/07, then 06 + example)  
2. `SKILL.md` workflow + hard gate + read order  
3. `/bmgen-eca-yaml` command  
4. Hook + settings permissions  
5. Manual acceptance T1–T4  

Phase 2 (out of this design): extract to installable plugin; optional generate-always path; multi-ECU.

---

## 7. Evidence index

| Claim | Evidence |
|-------|----------|
| Root shape apiVersion + ecu_mock.name + behavior | `parser.py` `parse_file`; fixture `schema_v2.yaml` |
| Signal form `[Bus]Frame.Signal` | `signals.py` `_SIGNAL_RE` |
| Frozen error codes | `diagnostics.py` `ERROR_CATALOG` |
| Provide/consume + MVP RX-only `$[…]` | `DESIGN_DECISIONS.md` A13–A16 |
| Handler per (bus, frame); timer order | `DESIGN_DECISIONS.md` A17–A19 |
| CLI parse/generate/verify/errors | `cli.py` |
| Output `__init__.py` + `__main__.py` only | `DESIGN_DECISIONS.md` M8 |

---

## 8. Open items resolved in brainstorm

| Question | Answer |
|----------|--------|
| Skill-only vs parse loop vs full agent | Parse loop (B) |
| Project vs plugin vs staged | Project-local (A) |
| Soft vs hard vs N-round auto-fix | Hard gate (A) |
| Approach | Skill + slash + hook (2) |
| Teaching depth | Graph + structs + domains + generated shape |

No remaining open product questions for phase 1.
