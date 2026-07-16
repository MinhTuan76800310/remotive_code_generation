# bmgen_ECA — Design decisions log

> **Purpose:** Frozen decisions from the design session. After build, re-read this file and tick **Acceptance** against the real package.
>
> **Status:** §1–§5 **approved**. Ready for implementation plan.
>
> **Date:** 2026-07-16  
> **Fixture:** [`workspace/passenger_welcome_eca/schema/schema_v2.yaml`](../workspace/passenger_welcome_eca/schema/schema_v2.yaml)  
> **User feedback file:** [`workspace/passenger_welcome_eca/tmp/user_feedback.md`](../workspace/passenger_welcome_eca/tmp/user_feedback.md)  
> **Legacy:** `workspace/passenger_welcome_eca/examples/door_ecu.yaml` (DoorECU open/close) **moved** to `examples/_legacy/door_ecu.yaml` — out of MVP scope.

---

## How to use after build

For each decision row: mark `✅` if build matches, `❌` + note if drifted, `⏭️` if deferred with reason.

Do **not** silently change a decision in code without updating this file.

---

## 0. Meta decisions (pre-architecture)

| ID | Decision | Choice | Rejected | Why | Acceptance after build |
|----|----------|--------|----------|-----|------------------------|
| M1 | Package placement | **New software** at `~/Desktop/tuan_dz/code_generation/bmgen_ECA` | Extend `remotive-bm-compiler/bmgen`; rewrite recipe IR | 2 independent products; no dialect bleed into WeightedLogOdds / ActuatorCommand | [ ] Package lives only under `bmgen_ECA/`; no import of recipe IR |
| M2 | MVP success bar | **Generate runnable door-stepping package** from schema_v2 | Parse-only; full Remotive E2E | Validate alone too thin; live bus too heavy for first cut | [ ] `generate schema_v2.yaml --out …` emits importable package |
| M3 | Expr scope | **`$state.x`, `$para.x`, `$[Bus]Frame.Signal` + min/max/abs/numeric ops** | Full Python eval; restricted eval | Enough for schema_v2; numpy handles min/max/abs cleanly | [ ] All schema_v2 exprs lower; no eval |
| M4 | Architecture approach | **A — Thin pipeline, IR = resolved ECA tree** | B single-pass walk; C reuse recipe templates+IR | Testable stages; typed handoffs; no recipe risk | [ ] Stages exist as separate modules |
| M5 | Math runtime | **`numpy`** for `min`/`max`/`abs` in lowered code | stdlib only; roll our own | Schema_v2 payloads are clamp-style arithmetic; numpy is the right hammer | [ ] Generated `__main__` `import numpy as np` and uses `np.minimum/maximum/abs` |
| M6 | Math operator lowering | `min(a, b, …)` → `np.minimum.reduce([a, b, …])`; `max` likewise; `abs(x)` → `np.abs(x)` | direct `min/max` (breaks when args are arrays later) | numpy.reduce matches variadic intent + future-proof | [ ] Codegen emits `np.minimum.reduce` for ≥2 args; `np.abs` for 1 arg |
| M7 | Output directory | **`bmgen_generated/`** under user `--out` | `out/<ecu>/` | Matches project convention used in `test_env/VF_child-detection/bmgen_generated/...` | [ ] Default `--out .` produces `bmgen_generated/<ecu>/` |
| M8 | Output files | `__init__.py` + `__main__.py` only | + `log.py` | Minimal artifact per user feedback | [ ] No log.py generated |
| M9 | Signal grouping for codegen | **One handler per `[Bus].Frame`** (not per signal, not per bus) | per signal; per bus | Remotive handler binds a FrameFilter to one frame; multiple signals on the same frame share state + order | [ ] `BodyCAN.DoorStatus` → single handler; signals `TargetPosition`, `CurrentPosition`, `IsMoving` all accessible |
| M10 | Old `examples/door_ecu.yaml` | **Move to `examples/_legacy/door_ecu.yaml`** — out of MVP | keep as alternative | schema_v2 owns new dialect; legacy preserved but not a generator target | [ ] File moved; no test references it as input |
| M11 | CLI extras | **`--help`** on every subcmd + **`bmgen-eca errors`** subcommand to list diagnostic catalog | none | User asked: where to read docs of errors | [ ] `--help` works; `bmgen-eca errors` prints the catalog from §4 |

### Wiki inputs that shaped M*

- Compiler = **analysis** tool, not only emitter → validate before codegen.
- **IR** = middleman between dialect and runtime.
- Ambiguity → **error**, not guess → forces prefixed `$state/$para/$[…]` over bare `$name`.
- Stages + **promotion gates** (fail → no ship).
- Legacy recipe model stays outside new ECA boundary.
- Structure lowered at compile time; Env values at runtime → condition becomes Python source.
- **Immutable typed artifacts** between stages; no shared mutable `ctx` dict bus.

---

## 1. Goal & scope (§1 — approved, **schema_v2 dialect**)

### Goal

`bmgen_ECA` compiles **schema_v2** ECU YAML → Remotive Behavioral Model Python package.

### MVP fixture (locked)

[`workspace/passenger_welcome_eca/schema/schema_v2.yaml`](../workspace/passenger_welcome_eca/schema/schema_v2.yaml) — *stepping door*:
- `ecu_mock.name: DoorECU` (required for package/class/SenderFilter)
- 1 RX: `[BodyCAN]DoorStatus.TargetPosition`
- 2 TX: `[BodyCAN]DoorStatus.CurrentPosition`, `[BodyCAN]DoorStatus.IsMoving`
- 4 params: `min_pos`, `max_pos`, `move_step`, `pos_tolerance`
- 3 state: `door_moving` (bool), `current_pos` (float), `target_pos` (float)
- 1 timer: `tick` (0.2s, auto_start)
- 3 rules: `receive_target` (on_rx, math clamp), `move_door` (on_timer tick, math step), `publish_status` (on_timer tick, math + 2 tx)

### In scope (MVP)

| ID | Item | Detail | Acceptance |
|----|------|--------|------------|
| S1.1 | Input dialect | `apiVersion` + `ecu_mock.name` + `behavior.{interfaces, parameters, state, timers, rules}` | [ ] |
| S1.2 | Signal id | `"[Bus]Frame.Signal"` parsed as 3-tuple | [ ] |
| S1.3 | Pipeline | Parse → SymbolTable → Resolve → Expr → Semantic → IR → Jinja → Verify | [ ] |
| S1.4 | Expr | `$state.x`, `$para.x`, `$[Bus]Frame.Signal`; numeric ops; `min/max/abs`; compare; bool ops; parens; literals | [ ] |
| S1.5 | Output layout | `bmgen_generated/<ecu>/{__init__.py, __main__.py}` | [ ] |
| S1.6 | CLI | `parse` / `generate --out` / `verify` + `--help` + `errors` subcmd | [ ] |
| S1.7 | Tests | Green schema_v2; **red** delete `$state.target_pos` / `[BodyCAN]DoorStatus.TargetPosition` / unknown function | [ ] |

### Out of scope (MVP) — must not block green path

| Item | Acceptance (absent or stub-reject) |
|------|-----------------------------------|
| `someip_tx` codegen | [ ] non-empty → warn `W_SOMEIP_IGNORED`; still generate |
| Topology / DBC | [ ] Not required to generate |
| Strings in expr | [ ] `E_BAD_EXPR` if encountered |
| Mixed-type arithmetic (e.g. `int + bool`) | [ ] reject for MVP |
| Arbitrary functions beyond `min/max/abs` | [ ] `E_UNKNOWN_FUNCTION` |
| `start_timer` action | [ ] reject |
| Recipe bmgen merge | [ ] No dep on `bmgen.recipes` |
| Multi-namespace / multi-broker | [ ] Single CanNamespace per ECU |
| Live Remotive bus test | [ ] Not blocking |

### What "green / red tests" mean (giải thích)

| Test | Mục đích |
|------|----------|
| **Green** | Compile **valid** YAML → success. Pipeline chạy đúng cho fixture. |
| **Red** | Cố tình **làm hỏng** fixture rồi compile. Generator **phải từ chối** + báo đúng code. Chứng minh: YAML sai → không có mock sai lưu hành. |

Ví dụ schema_v2:

| Red test | Sửa gì | Expected diag |
|----------|--------|----------------|
| Delete `state.target_pos` | Bỏ dòng khai báo | `E_UNRESOLVED_IDENT` trên rules dùng `$state.target_pos` |
| Delete `[BodyCAN]DoorStatus.TargetPosition` khỏi `can_rx` | Rule `receive_target` vẫn còn | `E_TRIGGER_TARGET` |
| Gõ `clamp(...)` trong payload | Thay `min/max` | `E_UNKNOWN_FUNCTION` |
| Xóa `init: 0.0` của `target_pos` | Bỏ init | `E_MISSING_INIT` |
| Đổi `interval: 0.2` thành `"abc"` | Bad type | `E_BAD_TIMER_INTERVAL` |

---

## 2. Architecture (§2 — approved; ecu_mock.name amendment)

### Pipeline (immutable handoffs)

```text
YAML text
  → parser        → RawEcu          (shape-checked dict / dataclass)
  → symbols       → SymbolTable     (frozen after build)
  → rules         → ResolvedModel   (every consumer bound; expr AST attached)
  → semantic      → ValidatedEcaIR | list[Diag]
  → codegen       → Artifacts       (file map under bmgen_generated/)
  → verify        → Report          (syntax + import smoke)
CLI / pipeline.py only orchestrates; stages do not share a mutable ctx dict.
```

| ID | Decision | Acceptance |
|----|----------|------------|
| A1 | Immutable handoffs; **no** shared mutable `ctx` dict across stages | [ ] Stages take typed args, return values |
| A2 | Symbol table **frozen** after build | [ ] No mutation API after freeze |
| A3 | Codegen accepts **only** `ValidatedEcaIR` | [ ] Cannot render unresolved model |
| A4 | Verify **observes**, does not fix artifacts | [ ] verify has no write-back to IR |
| A5 | Collect **all** semantic errors in one pass; any error → no codegen, exit 1 | [ ] Multi-error report possible |
| A6 | Warnings (unused param/state/timer, someip) still allow generate | [ ] W_* does not block emit |

### Package layout

```text
bmgen_ECA/
  DESIGN_DECISIONS.md
  pyproject.toml                 # name: bmgen-eca; deps: pyyaml, jinja2, numpy
  README.md
  src/bmgen_eca/
    __init__.py
    cli.py                       # parse | generate | verify | errors + --help
    pipeline.py                  # pure driver
    diagnostics.py               # Diag + frozen ERROR_CATALOG
    parser.py                    # YAML → RawEcu (behavior: root)
    signals.py                   # parse "[Bus]Frame.Signal" → SignalId(bus, frame, signal)
    symbols.py                   # providers: rx/tx/param/state/timer
    rules.py                     # bind trigger/condition/actions
    expr.py                      # lexer/parser/lower for $state/$para/$[Bus]Frame.Signal + min/max/abs
    semantic.py                  # provide/consume + kinds + unused warn
    ir.py                        # frozen dataclasses
    codegen/
      __init__.py                # render(ir) → Artifacts
      templates/
        main.py.j2
        init.py.j2
    verify.py
  tests/
    fixtures/
      schema_v2.yaml             # copy or symlink of workspace fixture
    test_signals.py
    test_symbols.py
    test_expr.py
    test_resolve_v2.py
    test_semantic_red.py
    test_codegen_v2.py
    test_pipeline_e2e.py
    test_diag_catalog.py
```

| ID | Decision | Acceptance |
|----|----------|------------|
| A7 | Import package `bmgen_eca`; console entry `bmgen-eca` | [ ] `pip install -e .` + entrypoint |
| A8 | One-way deps: `cli → pipeline → stages`; stages ↛ cli | [ ] No circular imports |
| A9 | Runtime **inspired by** recipe `main.py.j2`, **not** shared templates | [ ] Own templates under `bmgen_eca/codegen/templates` |
| A10 | `signals.py` owns SignalId parse/validate (3-tuple) | [ ] Used by symbols + rules + expr |
| A11 | `expr.py` is its own stage module (lexer + AST + lower) | [ ] Unit-tested without full pipeline |
| A12 | Dependency on `numpy` is **codegen/runtime** of generated BM, not required inside compiler stages except lower string emit | [ ] Compiler unit tests do not need Remotive; generated code imports numpy |

### Provide / consume (non-negotiable)

```text
PROVIDERS:
  can_rx[signal]     → SignalId  (kind RX)
  can_tx[signal]     → SignalId  (kind TX)
  parameters[name]   → kind PARAM
  state[name]        → kind STATE
  timers[name]       → kind TIMER

CONSUMERS:
  trigger.target          (on_rx → RX SignalId | on_timer → TIMER name)
  $state.<name>           → STATE
  $para.<name>            → PARAM
  $[Bus]Frame.Signal      → RX (read in condition/payload)  [MVP: RX only for $signal]
  action set_state.target → STATE
  action tx.target        → TX SignalId

ambiguous / bare $name without prefix → E_BAD_EXPR (schema_v2 requires prefix)
```

| ID | Decision | Acceptance |
|----|----------|------------|
| A13 | Bare `$name` (schema_Nhan style) is **invalid** in schema_v2 | [ ] `E_BAD_EXPR` or `E_BARE_IDENT` |
| A14 | `$[Bus]Frame.Signal` in expr must resolve to a declared **can_rx** (MVP) | [ ] TX not readable via `$[…]` unless also in can_rx |
| A15 | `on_rx.target` must be full `"[Bus]Frame.Signal"` matching can_rx entry | [ ] |
| A16 | `tx.target` must match can_tx entry exactly (same string form) | [ ] |

### Handler / timer grouping (codegen shape)

| ID | Decision | Acceptance |
|----|----------|------------|
| A17 | **One handler per `(bus, frame)`** — Remotive `FrameFilter(frame)` | [ ] DoorStatus → one `on_DoorStatus` |
| A18 | Multiple `on_rx` rules on same frame run **YAML source_order** (fire-all) | [ ] |
| A19 | Multiple `on_timer` rules on same timer run **YAML source_order** in one ticker loop | [ ] `tick` fires `move_door` then `publish_status` if that is YAML order |
| A20 | Namespace MVP: **CanNamespace name = `SignalId.bus`** (e.g. `BodyCAN`). Not `{ecu}-Can0`. | [ ] `CanNamespace("BodyCAN", …)` |
| A21 | ECU package/module name: **from `ecu_mock.name` only** (required) | [ ] `DoorECU` → dir `door_ecu`, class `DoorECU` |

### ECU name policy (updated 2026-07-16 after user edit)

schema_v2 now has:

```yaml
apiVersion: v1.0
ecu_mock:
  name: DoorECU
behavior:
  ...
```

| ID | Decision | Acceptance |
|----|----------|------------|
| A22 | **`ecu_mock.name` is required** — model class, package dir, `SenderFilter(ecu_name=…)` | [ ] Missing → `E_PARSE` / `E_MISSING_ECU_NAME` |
| A23 | ~~file stem fallback~~ **removed** — name comes only from YAML | [ ] No stem-based naming |
| A24 | Python package dir = snake_case(`DoorECU` → `door_ecu`); class name = as-written PascalCase `DoorECU` | [ ] `bmgen_generated/door_ecu/{__init__,__main__}.py` + `class DoorECU` |
| A25 | Root shape is `apiVersion` + `ecu_mock.name` + `behavior:` (not bare `behavior:` only) | [ ] parser enforces |

### Error policy (preview; full catalog §4)

- Collect all diags in semantic (+ parse/expr errors attached).
- Any `error` severity → no codegen, exit 1.
- `warning` → still generate.
- Codes frozen public contract (see §4).

### Dependency graph

```text
cli → pipeline → {parser, symbols, rules, semantic, codegen, verify}
rules → expr, symbols, signals
expr → signals, symbols (lookup only)
semantic → ir
codegen → ir
# no cycles; no stage imports cli
```

---

## 3. Data model & algorithms (§3 — approved)

### Core types (`ir.py` / `signals.py`, frozen)

```text
SignalId:
  bus: str          # "BodyCAN"
  frame: str        # "DoorStatus"
  signal: str       # "TargetPosition"
  raw: str          # "[BodyCAN]DoorStatus.TargetPosition"
  # parse: ^\[([^\]]+)\]([^.]+)\.(.+)$

SymbolKind = RX | TX | PARAM | STATE | TIMER

Symbol:
  name: str                 # param/state/timer short name OR SignalId.raw for rx/tx
  kind: SymbolKind
  type_name: str | None     # bool|int|float (MVP)
  meta: ...                 # value | init | interval | auto_start | signal_id

SymbolTable:                # frozen after build
  by_name: Mapping[str, Symbol]
  lookup_state(name) -> Symbol | Missing
  lookup_param(name) -> Symbol | Missing
  lookup_rx(signal_id) -> Symbol | Missing
  lookup_tx(signal_id) -> Symbol | Missing
  lookup_timer(name) -> Symbol | Missing

ExprAST:
  Lit(value: bool|int|float)
  StateRef(name) | ParamRef(name) | SignalRef(SignalId)
  UnaryOp(op: -, operand)
  BinOp(op: +|-|*|/, left, right)
  Compare(op: ==|!=|>|>=|<|<=, left, right)
  BoolOp(op: and|or, left, right)
  Call(fn: min|max|abs, args: list[ExprAST])

ActionIR:
  kind: set_state | tx
  target: Symbol            # STATE or TX
  payload: ExprAST

RuleIR:
  rule_id: str
  trigger: OnRx(SignalId) | OnTimer(timer_name)
  condition: ExprAST
  actions: list[ActionIR]
  source_order: int

ValidatedEcaIR:
  ecu_name: str             # from ecu_mock.name, e.g. DoorECU
  package_dir: str          # snake_case → door_ecu
  namespace: str            # = SignalId.bus (e.g. BodyCAN) — Remotive CanNamespace name
  symbols: SymbolTable
  params / states / timers: list[Symbol]
  rules: list[RuleIR]       # YAML order
  rx_frames: dict[(bus, frame), list[RuleIR]]   # group on_rx for handlers
  timer_rules: dict[timer_name, list[RuleIR]]
```

### Algorithms

**1. SignalId parse** (`signals.py`)  
Regex `^\[([^\]]+)\]([^.]+)\.(.+)$` → (bus, frame, signal). Fail → `E_BAD_SIGNAL_ID`.

**2. Symbol build**  
Declare all providers first. Dup name (param/state/timer/rule_id) → `E_DUP_SYMBOL`.  
RX/TX keyed by full raw string `"[Bus]Frame.Signal"`.

**3. `$…` resolve (schema_v2 — prefix required)**  

| Form | Lookup |
|------|--------|
| `$state.<name>` | STATE only |
| `$para.<name>` | PARAM only |
| `$[Bus]Frame.Signal` | can_rx only (MVP) |
| bare `$name` / `$name.x` without prefix | `E_BARE_IDENT` |

Missing → `E_UNRESOLVED_IDENT` with symbol field set to the full `$…` text.

**4. Expr parse**  
Recursive-descent / precedence:  
`or` < `and` < compare < `+ -` < `* /` < unary `-` < call/primary.  
Primary: lit | `$state…` | `$para…` | `$[…]` | `(expr)` | `min|max|abs(…)`  
Unknown call name → `E_UNKNOWN_FUNCTION`.

**5. Expr lower → Python source**  

| AST | Python |
|-----|--------|
| `$state.x` | `self.x` |
| `$para.x` | `self.x` (param as instance/const attr) |
| `$[Bus]Frame.Signal` | local from frame, e.g. `target_position` (snake of signal leaf) |
| `min(a,b,…)` | `np.minimum.reduce([a, b, …])` |
| `max(…)` | `np.maximum.reduce([…])` |
| `abs(x)` | `np.abs(x)` |
| `true`/`false` | `True`/`False` |
| `and`/`or` | `and`/`or` |

**6. Rule resolve**  
Per rule: bind trigger (kind check), parse condition + each payload, collect free refs, bind action targets.

**7. Semantic kind edges**

| Consumer | Allowed |
|----------|---------|
| `on_rx.target` | RX SignalId |
| `on_timer.target` | TIMER |
| `set_state.target` | STATE |
| `tx.target` | TX SignalId |
| `$state` / `$para` / `$[rx]` | as above |

**8. Group for codegen**  
`on_rx` → group by `(bus, frame)` → one handler.  
`on_timer` → one asyncio ticker per timer; fire rules in `source_order`.  
schema_v2: timer `tick` runs `move_door` then `publish_status` (YAML order).

### Error codes used by §3 (full catalog §4)

`E_BAD_SIGNAL_ID`, `E_DUP_SYMBOL`, `E_BARE_IDENT`, `E_UNRESOLVED_IDENT`, `E_UNKNOWN_FUNCTION`, `E_TRIGGER_TARGET`, `E_TX_TARGET_NOT_IN_CAN_TX`, `E_SET_STATE_UNKNOWN`, `E_BAD_EXPR`, `E_BAD_ACTION`, `E_BAD_TRIGGER_TYPE`, `E_MISSING_ECU_NAME`, `E_MISSING_INIT`, `E_BAD_TIMER_INTERVAL`, `W_UNUSED_*`, `W_SOMEIP_IGNORED`.

### MVP tests (must exist)

| Test | Assert |
|------|--------|
| `test_signal_id_parse` | `[BodyCAN]DoorStatus.TargetPosition` → bus/frame/signal |
| `test_v2_symbols` | 1 rx, 2 tx, 4 param, 3 state, 1 timer |
| `test_v2_resolve_3_rules` | all 3 rules bind |
| `test_expr_clamp_payload` | receive_target payload lowers with `np.minimum/maximum` |
| `test_red_delete_target_pos` | `E_UNRESOLVED_IDENT` |
| `test_red_delete_rx_signal` | `E_TRIGGER_TARGET` |
| `test_red_unknown_fn` | `E_UNKNOWN_FUNCTION` |
| `test_codegen_syntax` | `ast.parse` generated `__main__` |
| `test_pipeline_generate` | `bmgen_generated/door_ecu/{__init__,__main__}.py` exist |

| ID | Decision | Acceptance |
|----|----------|------------|
| D1 | SignalId 3-tuple parse strict | [ ] |
| D2 | Prefixed `$` only; bare → `E_BARE_IDENT` | [ ] |
| D3 | `$[…]` reads **can_rx only** (MVP) | [ ] |
| D4 | Expr lower compile-time → Python; no runtime interpreter | [ ] |
| D5 | min/max/abs → numpy as M5/M6 | [ ] |
| D6 | Group on_rx by (bus, frame); timer rules by timer name, YAML order | [ ] |
| D7 | `ecu_mock.name` → package_dir snake_case + class as-written | [ ] |
| D8 | **CanNamespace name = `SignalId.bus`** (e.g. `BodyCAN`). All signals on same bus share one namespace. Multi-bus = multi-namespace later (out of MVP if fixture is single-bus) | [ ] Generated `CanNamespace("BodyCAN", …)` |
| D9 | If an ECU declares signals on **multiple** buses in MVP → `E_MULTI_BUS_UNSUPPORTED` (or warn + use first bus only). schema_v2 is single-bus → green path | [ ] |

---

## 4. Diagnostics & CLI UX (§4 — approved)

### Principles

| ID | Decision | Acceptance |
|----|----------|------------|
| E1 | Diags → **stderr**; IR dump / write paths → **stdout** | [ ] |
| E2 | Collect all errors (cap 50); any error → no codegen, exit 1 | [ ] |
| E3 | Warnings do not block generate | [ ] |
| E4 | MVP text format only; `--json-diags` later | [ ] |
| E5 | **Error codes are a frozen public contract** — stable strings | [ ] codes match catalog |
| E6 | Same YAML + same compiler → **same multiset of (code, rule_id, symbol)** | [ ] snapshot tests |
| E7 | `bmgen-eca errors` prints this catalog (code + severity + when + help) | [ ] |

### Frozen error-code catalog (public API)

> **Rule:** codes are identifiers. Message English may improve; **code strings must not change** without version bump + note here.
>
> Storage: `src/bmgen_eca/diagnostics.py` as constants; tests assert exact code strings.

| Code | Severity | When | Required fields | help (fixed intent) |
|------|----------|------|-----------------|---------------------|
| `E_PARSE` | error | YAML load / missing `behavior` / bad shape | path | fix YAML to schema_v2 shape |
| `E_MISSING_ECU_NAME` | error | missing `ecu_mock.name` | path | set `ecu_mock.name` |
| `E_BAD_SIGNAL_ID` | error | signal not matching `[Bus]Frame.Signal` | symbol, path | use `[Bus]Frame.Signal` form |
| `E_DUP_SYMBOL` | error | duplicate param/state/timer name or `rule_id` | symbol | rename for uniqueness |
| `E_BARE_IDENT` | error | `$name` without `state.`/`para.`/`[Bus]…` | symbol, rule_id? | use `$state.x` / `$para.x` / `$[Bus]Frame.Signal` |
| `E_UNRESOLVED_IDENT` | error | `$state/$para/$[…]` not in symbol table | symbol, rule_id? | declare provider or remove ref |
| `E_UNKNOWN_FUNCTION` | error | call not in {min, max, abs} | symbol?, rule_id? | only min/max/abs allowed |
| `E_TRIGGER_TARGET` | error | on_rx∉can_rx or on_timer∉timers | symbol, rule_id | point trigger at declared rx/timer |
| `E_TX_TARGET_NOT_IN_CAN_TX` | error | tx target not in can_tx | symbol, rule_id | add to can_tx or fix target |
| `E_SET_STATE_UNKNOWN` | error | set_state target not in state | symbol, rule_id | add to state or fix target |
| `E_BAD_EXPR` | error | expr syntax / ops outside MVP | rule_id?, symbol? | see expr surface §1 |
| `E_BAD_ACTION` | error | action.type not tx\|set_state | rule_id | use tx or set_state |
| `E_BAD_TRIGGER_TYPE` | error | trigger.type not on_rx\|on_timer | rule_id | use on_rx or on_timer |
| `E_MISSING_INIT` | error | state entry missing `init` | symbol | provide init |
| `E_BAD_TIMER_INTERVAL` | error | interval not positive number | symbol | interval > 0 float seconds |
| `E_MULTI_BUS_UNSUPPORTED` | error | >1 distinct bus in interfaces (MVP) | path | single bus only in MVP |
| `W_UNUSED_PARAM` | warning | param never referenced | symbol | ok if documentation-only |
| `W_UNUSED_STATE` | warning | state never read/written | symbol | remove or use |
| `W_UNUSED_TIMER` | warning | timer never on_timer target | symbol | remove or add rule |
| `W_SOMEIP_IGNORED` | warning | non-empty someip_tx | — | MVP does not codegen SOME/IP |

**Determinism:**

1. Sort diags by `(path, rule_id or "", code, symbol or "")`.
2. No timestamps / absolute host paths / random ids in primary line.
3. Snapshot tests lock **code + rule_id + symbol** triples.
4. New code = append to table. Rename/remove = breaking.

### Human stderr format

```text
error[E_UNRESOLVED_IDENT]: unresolved `$state.target_pos`
  --> schema_v2.yaml  rule=move_door  symbol=$state.target_pos
  help: declare it under behavior.state or remove the ref

error: aborting due to N errors; M warnings; no code generated
```

Primary line **must** start with `error[CODE]:` or `warning[CODE]:`.

### CLI

| Cmd | stdout | stderr | exit |
|-----|--------|--------|------|
| `bmgen-eca parse <yaml>` | IR summary | diags | 1 if error |
| `bmgen-eca generate <yaml> --out D` | wrote `D/bmgen_generated/door_ecu/…` | diags | 1 if error (**no write**) |
| `bmgen-eca verify <dir>` | ok/fail | diags | 1 if fail |
| `bmgen-eca errors` | catalog table | — | 0 |
| `bmgen-eca --help` / subcmd `--help` | help text | — | 0 |

### Diag tests

| Test | Assert |
|------|--------|
| `test_red_delete_target_pos` | code exactly `E_UNRESOLVED_IDENT` |
| `test_red_delete_rx` | code exactly `E_TRIGGER_TARGET` |
| `test_red_unknown_fn` | code exactly `E_UNKNOWN_FUNCTION` |
| `test_diag_codes_are_catalog` | every emitted code ∈ frozen set |
| `test_diag_order_deterministic` | twice same broken YAML → identical code stream |
| `test_errors_subcommand` | `bmgen-eca errors` lists all codes |

---

## 5. Codegen / Remotive surface (§5 — approved)

### Artifact layout

```text
{--out}/
  bmgen_generated/
    door_ecu/                 # snake_case(ecu_mock.name)
      __init__.py
      __main__.py
```

No `log.py` (M8).

| ID | Decision | Acceptance |
|----|----------|------------|
| C1 | Output root = `{--out}/bmgen_generated/<package_dir>/` | [ ] |
| C2 | Files: `__init__.py` + `__main__.py` only | [ ] |
| C3 | Jinja templates owned by `bmgen_eca/codegen/templates/` — not shared with recipe bmgen | [ ] |
| C4 | Generated code deterministic: stable order, no timestamps | [ ] |

### Remotive API surface (emit these)

| Use | API |
|-----|-----|
| Broker | `BrokerClient(url=avp.url, auth=avp.auth)` |
| Namespace | `CanNamespace("<bus>", broker, restbus_configs=[RestbusConfig([filters.SenderFilter(ecu_name="<ecu_mock.name>")], delay_multiplier=avp.delay_multiplier)])` |
| Model host | `BehavioralModel(ecu_name, namespaces=[…], broker_client=…, input_handlers=[…])` |
| RX | `ns.create_input_handler([filters.FrameFilter("<frame>")], model.on_<Frame>)` |
| TX | `await self.<ns_var>.restbus.update_signals(("<SignalId.raw or Frame.Signal>", value), …)` |
| Args | `BehavioralModelArgs.parse()` + `asyncio.run(main(args))` |
| Tickers | `asyncio.create_task` + `await asyncio.sleep(interval)` (auto_start before `run_forever`) |
| Math | `import numpy as np` |

### Namespace = bus (from §3 D8)

| ID | Decision | Acceptance |
|----|----------|------------|
| C5 | `CanNamespace` name = `SignalId.bus` e.g. `"BodyCAN"` | [ ] |
| C6 | Python ns var = snake_case(bus) e.g. `body_can` | [ ] |
| C7 | Restbus `SenderFilter(ecu_name=ecu_mock.name)` e.g. `"DoorECU"` | [ ] |
| C8 | Single bus only in MVP (`E_MULTI_BUS_UNSUPPORTED` if >1) | [ ] |

### Handler grouping = (bus, frame)

| ID | Decision | Acceptance |
|----|----------|------------|
| C9 | One async handler per frame: `async def on_DoorStatus(self, frame: Frame)` | [ ] |
| C10 | `FrameFilter("DoorStatus")` — frame part only (Remotive frame name) | [ ] |
| C11 | On entry: read each RX signal leaf used by rules on this frame into locals | [ ] |
| C12 | Fire `on_rx` rules for that frame in `source_order` | [ ] |

**Signal key in `frame.signals`:** prefer full raw `"[BodyCAN]DoorStatus.TargetPosition"` first; if Remotive topology uses short `"DoorStatus.TargetPosition"` or leaf only, document adapter once. MVP emit **raw SignalId string** as key; live-bus mismatch is post-MVP (structural package still valid).

### Timer = free-running ticker

| ID | Decision | Acceptance |
|----|----------|------------|
| C13 | One `asyncio` task per timer with `auto_start: true` | [ ] |
| C14 | Loop: `await asyncio.sleep(interval)` then fire all `on_timer` rules for that timer in YAML order | [ ] |
| C15 | schema_v2 `tick` @ 0.2s: `move_door` then `publish_status` | [ ] |
| C16 | Start tickers after model construct, before `bm.run_forever()` | [ ] |

### Action lowering

| Action | Generated |
|--------|-----------|
| `set_state` target=X payload=E | `self.X = <lower(E)>` |
| `tx` target=S payload=E | `await self.<ns>.restbus.update_signals((key, <lower(E)>), …)` |

Consecutive `tx` in same rule may batch into one `update_signals` call.

### DoorECU (schema_v2) sketch

```text
import asyncio, logging
import numpy as np
from remotivelabs.broker import BrokerClient, Frame
from remotivelabs.topology.behavioral_model import BehavioralModel
from remotivelabs.topology.cli.behavioral_model import BehavioralModelArgs
from remotivelabs.topology.namespaces import filters
from remotivelabs.topology.namespaces.can import CanNamespace, RestbusConfig

class DoorECU:
    body_can: CanNamespace
    min_pos: float = 0.0
    max_pos: float = 100.0
    move_step: float = 10.0
    pos_tolerance: float = 0.01
    door_moving: bool = False
    current_pos: float = 0.0
    target_pos: float = 0.0
    _ticker_tick: asyncio.Task | None = None

    def __init__(self, body_can: CanNamespace) -> None:
        self.body_can = body_can

    async def on_DoorStatus(self, frame: Frame) -> None:
        target_position = frame.signals["[BodyCAN]DoorStatus.TargetPosition"]
        # rule receive_target (condition true)
        self.target_pos = np.maximum.reduce([
            self.min_pos,
            np.minimum.reduce([self.max_pos, target_position]),
        ])

    async def _loop_tick(self) -> None:
        while True:
            await asyncio.sleep(0.2)
            # move_door
            if abs(self.target_pos - self.current_pos) > self.pos_tolerance:  # or np.abs
                self.current_pos = self.current_pos + np.maximum.reduce([
                    0 - self.move_step,
                    np.minimum.reduce([
                        self.move_step,
                        self.target_pos - self.current_pos,
                    ]),
                ])
            # publish_status (always)
            self.door_moving = bool(
                np.abs(self.target_pos - self.current_pos) > self.pos_tolerance
            )
            await self.body_can.restbus.update_signals(
                ("[BodyCAN]DoorStatus.CurrentPosition", self.current_pos),
                ("[BodyCAN]DoorStatus.IsMoving", self.door_moving),
            )

    def _start_tickers(self) -> None:
        self._ticker_tick = asyncio.create_task(self._loop_tick())

async def main(avp: BehavioralModelArgs):
    async with BrokerClient(url=avp.url, auth=avp.auth) as broker_client:
        body_can = CanNamespace(
            "BodyCAN",
            broker_client,
            restbus_configs=[RestbusConfig(
                [filters.SenderFilter(ecu_name="DoorECU")],
                delay_multiplier=avp.delay_multiplier,
            )],
        )
        door_ecu = DoorECU(body_can=body_can)
        async with BehavioralModel(
            "DoorECU",
            namespaces=[body_can],
            broker_client=broker_client,
            input_handlers=[
                body_can.create_input_handler(
                    [filters.FrameFilter("DoorStatus")],
                    door_ecu.on_DoorStatus,
                ),
            ],
        ) as bm:
            door_ecu._start_tickers()
            await bm.run_forever()

if __name__ == "__main__":
    args = BehavioralModelArgs.parse()
    logging.basicConfig(level=args.loglevel)
    asyncio.run(main(args))
```

### Verify gate

| ID | Decision | Acceptance |
|----|----------|------------|
| C17 | `verify`: `ast.parse` every `.py` under package | [ ] |
| C18 | Optional importlib load without broker connect (smoke) | [ ] |
| C19 | Does **not** require live Remotive for MVP pass | [ ] |

### Explicit non-goals in templates

- Multi-namespace / multi-broker  
- Reboot/control handlers  
- Websocket  
- Recipe pattern includes  
- `log.py`

### Risk accepted for MVP

Frame signal **dict key** shape depends on Remotive frame defs. Emit raw `[Bus]Frame.Signal`; topology alignment later. Acceptance = structural package + lowered logic correctness, not live bus E2E.

---


## 5b. Design self-review (pre-plan)

| Check | Result |
|-------|--------|
| 1. Placeholder / TBD left? | Only drift log empty (OK). §2–§5 filled. |
| 2. Internal contradictions? | Fixed: ecu name = `ecu_mock.name` (not stem); namespace = `bus` (not `{ecu}-Can0`); group by (bus, frame); no log.py; out = `bmgen_generated/`. |
| 3. Scope creep vs MVP? | Live Remotive E2E, multi-bus, someip, recipe merge = out. Good. |
| 4. Ambiguity for implementer? | Signal key in `frame.signals` still runtime-dependent — documented as accepted risk. Expr grammar full enough for schema_v2 clamp/step. |
| 5. Fixture completeness? | schema_v2 exercises: on_rx, on_timer fire-all order, min/max/abs, $state/$para/$[rx], set_state, multi-tx. |
| 6. Fail-closed provide/consume? | Yes — red tests + frozen codes. |
| 7. Two-software boundary? | `bmgen_ECA` no import of recipe `bmgen.*`. |

**Gaps intentionally deferred (not blockers):**
- Exact Remotive signal dict key at runtime
- Optional `--json-diags`
- Multi-bus

**Ready for writing-plans.**

---
## 6. Drift log (fill during/after build)

| Date | Decision ID | What code did | Match? | Action |
|------|-------------|----------------|--------|--------|
| | | | | |

---

## 7. Sign-off

| Role | Name | Date | Note |
|------|------|------|------|
| Design §1 (schema_v2) | user + agent | 2026-07-16 | Approach A; package `bmgen_ECA`; MVP = stepping door |
| Design §2 | user + agent | 2026-07-16 | Architecture; `ecu_mock.name: DoorECU` required |
| Design §3 | user + agent | 2026-07-16 | Data model; bus → Remotive CanNamespace |
| Design §4 | user + agent | 2026-07-16 | Frozen error catalog + CLI `errors` |
| Design §5 | user + agent | 2026-07-16 | Codegen; bus=CanNamespace; FrameFilter; numpy |
| Post-build review | | | Compare checkboxes above to tree + tests |
