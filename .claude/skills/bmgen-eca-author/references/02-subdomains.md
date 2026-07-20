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

---

## On same timer: service order

When several `on_timer` rules share one timer, they fire one by one inside a
single ticker loop, in YAML source order. Use this to compose state machines
across one tick:

- **read-then-write** — rule N reads a state, rule N+1 writes it (typical `step` → `update_level`).
- **publish-then-decay** — TX while a counter is high, then decrement next rule.
- **arm-then-publish** — arm a pulse budget, then publish reads the new value this cycle.

Rule order is the *contract* for what happens within a single tick. Conditions
enforce when a rule fires, but YAML order determines **the sequence inside one
loop body**. See [`08-pulse-done.md`](08-pulse-done.md) for a worked example.

Anti-pattern: relying on condition alone to enforce order between two rules.
