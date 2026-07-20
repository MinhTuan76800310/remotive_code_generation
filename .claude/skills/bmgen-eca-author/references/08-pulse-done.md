# Pulse IsDone (edge-from-level state machine)

Use when an actuator must emit a short **edge** on arrival (e.g. `IsDone` true for
~200 ms, then false) so that other nodes detect a `1→0` transition. Remotive restbus
is sticky while a cyclic restbus owner is active — emit a short pulse then drop to 0
yourself.

Dialect support: **no new primitive needed**. Just `state` + `on_timer` + `set_state`
+ `tx` + compare. The trick is **latched previous-tick state** (`was_*`) and a
**pulse budget counter** (`*_pulse_left`) wired across multiple on_timer rules.

## Live evidence (DBC `GenMsgCycleTime = 50 ms`)

Door tick = 0.2 s = 4 × 50 ms. Seat tick = 0.1 s. To make a pulse **observable** on
the bus, the high window must span ≥ 4 restbus cycles:

```text
pulse_ticks × timer_interval  ≥  4 × DBC GenMsgCycleTime
```

Door: `1 × 0.2 = 0.2 s` ≥ `4 × 0.05 = 0.2 s` → OK
Seat: `2 × 0.1 = 0.2 s` ≥ `4 × 0.05 = 0.2 s` → OK

If pulse is shorter than that, tests that wait for `{IsDone: 1.0}` may race and miss.

## Door recipe (one-tick pulse)

```yaml
parameters:
  - name: move_step
    type: float
    value: 10.0
  - name: pos_tolerance
    type: float
    value: 0.01
  - name: done_pulse_ticks
    type: int
    value: 1              # 1 × 0.2s = 200ms high

state:
  - {name: door_moving,      type: bool,  init: false}
  - {name: was_moving,       type: bool,  init: false}   # prev-tick level
  - {name: current_pos,      type: float, init: 0.0}
  - {name: target_pos,       type: float, init: 0.0}
  - {name: done_pulse_left,  type: int,   init: 0}      # ticks remaining with IsDone=1

timers:
  - {name: tick, interval: 0.2, auto_start: true}

rules:                   # YAML source order — matters per ticker loop
  - rule_id: receive_target        # on_rx → clamp
    trigger: {type: on_rx,   target: "[DoorECU-BodyCan0]DoorCmd.TargetPosition"}
    condition: "true"
    actions:
      - {type: set_state, target: target_pos, payload: "max($para.min_pos, min($para.max_pos, $[DoorECU-BodyCan0]DoorCmd.TargetPosition))"}

  - rule_id: move_door             # step current_pos
    trigger: {type: on_timer, target: tick}
    condition: "abs($state.target_pos - $state.current_pos) > $para.pos_tolerance"
    actions:
      - {type: set_state, target: current_pos, payload: "$state.current_pos + max(0 - $para.move_step, min($para.move_step, $state.target_pos - $state.current_pos))"}

  - rule_id: update_moving         # recompute level AFTER step
    trigger: {type: on_timer, target: tick}
    condition: "true"
    actions:
      - {type: set_state, target: door_moving, payload: "abs($state.target_pos - $state.current_pos) > $para.pos_tolerance"}

  - rule_id: arm_done_pulse        # 1→0 edge → arm
    trigger: {type: on_timer, target: tick}
    condition: "$state.was_moving == true and $state.door_moving == false and $state.done_pulse_left == 0"
    actions:
      - {type: set_state, target: done_pulse_left, payload: "$para.done_pulse_ticks"}

  - rule_id: publish_status        # TX IsDone only while budget still high
    trigger: {type: on_timer, target: tick}
    condition: "true"
    actions:
      - {type: tx, target: "[DoorECU-BodyCan0]DoorStatus.CurrentPosition", payload: "$state.current_pos"}
      - {type: tx, target: "[DoorECU-BodyCan0]DoorStatus.IsMoving",      payload: "$state.door_moving"}
      - {type: tx, target: "[DoorECU-BodyCan0]DoorStatus.IsDone",        payload: "$state.done_pulse_left > 0"}

  - rule_id: decay_done_pulse      # consume budget AFTER publish
    trigger: {type: on_timer, target: tick}
    condition: "$state.done_pulse_left > 0"
    actions:
      - {type: set_state, target: done_pulse_left, payload: "$state.done_pulse_left - 1"}

  - rule_id: latch_was_moving      # store NEW level for next-tick edge
    trigger: {type: on_timer, target: tick}
    condition: "true"
    actions:
      - {type: set_state, target: was_moving, payload: "$state.door_moving"}
```

### Why rule order matters here

| Slot | Reads | Writes | Purpose |
|------|-------|--------|---------|
| `move_door` | `current_pos` | `current_pos` | step first |
| `update_moving` | `current_pos, target_pos` | `door_moving` | recompute level |
| `arm_done_pulse` | `was_moving, door_moving, done_pulse_left` | `done_pulse_left` | edge set new budget |
| `publish_status` | `current_pos, door_moving, done_pulse_left` | (TX only) | must run **before** decay |
| `decay_done_pulse` | `done_pulse_left` | `done_pulse_left` | must run **after** publish |
| `latch_was_moving` | `door_moving` | `was_moving` | must run **last** (record new level) |

If you swap publish and decay, the high window collapses to 0 next cycle.

## Seat recipe (multi-tick pulse + startup FSM + retarget reset)

Adds three ideas on top of the door recipe:

- `startup_ticks_left` countdown between accept and step (real actuator settle delay).
- Two `done_*` flags instead of edge memory: `seat_moving` (motion active) +
  `seat_target` (latched target). Retarget is detected by comparing incoming
  `SeatPosTarget` with `seat_target`.
- `done_active` is the pulse FSM armed flag; `done_pulse_left` is the budget.

```yaml
parameters:
  - {name: move_step,        type: int, value: 1}
  - {name: startup_ticks,    type: int, value: 20}     # 20 × 0.1s = 2s startup
  - {name: done_pulse_ticks, type: int, value: 2}      # 2 × 0.1s = 200ms high

state:
  - {name: seat_pos,          type: int,  init: 0}
  - {name: seat_target,       type: int,  init: 0}
  - {name: seat_moving,       type: bool, init: false}
  - {name: startup_ticks_left,type: int,  init: 0}
  - {name: done_active,       type: bool, init: false}
  - {name: done_pulse_left,   type: int,  init: 0}

timers:
  - {name: move_tick, interval: 0.1, auto_start: true}

rules:
  # on_rx — accept target and clear prior pulse. TX IsDone=false is here
  # (not just inside complete_seat_move) so retarget during move is visible.
  - rule_id: accept_seat_target
    trigger: {type: on_rx, target: "[SeatECU-BodyCan0]PW_SeatCmd.SeatPosTarget"}
    condition: "$[SeatECU-BodyCan0]PW_SeatCmd.SeatPosTarget != $state.seat_pos and $[SeatECU-BodyCan0]PW_SeatCmd.SeatPosTarget != $state.seat_target"
    actions:
      - {type: set_state, target: seat_target,         payload: "$[SeatECU-BodyCan0]PW_SeatCmd.SeatPosTarget"}
      - {type: set_state, target: seat_moving,         payload: "true"}
      - {type: set_state, target: done_active,         payload: "false"}
      - {type: set_state, target: done_pulse_left,     payload: "0"}
      - {type: tx,        target: "[SeatECU-BodyCan0]PW_SeatStatus.IsDone", payload: "false"}
      - {type: set_state, target: startup_ticks_left,  payload: "$para.startup_ticks"}

  # on_timer ordering for `move_tick` (matters):
  - rule_id: startup_countdown
    trigger: {type: on_timer, target: move_tick}
    condition: "$state.seat_moving == true and $state.startup_ticks_left > 0"
    actions:
      - {type: set_state, target: startup_ticks_left, payload: "$state.startup_ticks_left - 1"}

  - rule_id: step_seat_pos
    trigger: {type: on_timer, target: move_tick}
    condition: "$state.seat_moving == true and $state.startup_ticks_left == 0 and $state.seat_pos != $state.seat_target"
    actions:
      - {type: set_state, target: seat_pos, payload: "$state.seat_pos + max(0 - $para.move_step, min($para.move_step, $state.seat_target - $state.seat_pos))"}
      - {type: tx,        target: "[SeatECU-BodyCan0]PW_SeatStatus.SeatPosition", payload: "$state.seat_pos"}

  - rule_id: complete_seat_move   # arm pulse budget
    trigger: {type: on_timer, target: move_tick}
    condition: "$state.seat_moving == true and $state.startup_ticks_left == 0 and $state.seat_pos == $state.seat_target"
    actions:
      - {type: set_state, target: seat_moving,     payload: "false"}
      - {type: set_state, target: done_active,     payload: "true"}
      - {type: set_state, target: done_pulse_left, payload: "$para.done_pulse_ticks"}

  # Pulse service (must run AFTER complete_seat_move in YAML order):
  - rule_id: service_done_pulse_end    # one-shot end: left==0 → TX false, disarm
    trigger: {type: on_timer, target: move_tick}
    condition: "$state.done_active == true and $state.done_pulse_left == 0"
    actions:
      - {type: tx,        target: "[SeatECU-BodyCan0]PW_SeatStatus.IsDone", payload: "false"}
      - {type: set_state, target: done_active, payload: "false"}

  - rule_id: service_done_pulse_high   # left>0 → TX true, decrement
    trigger: {type: on_timer, target: move_tick}
    condition: "$state.done_pulse_left > 0"
    actions:
      - {type: tx,        target: "[SeatECU-BodyCan0]PW_SeatStatus.IsDone", payload: "true"}
      - {type: set_state, target: done_pulse_left, payload: "$state.done_pulse_left - 1"}
```

Retarget-during-move is handled entirely by `accept_seat_target` — its condition
matches any new target while one is already latched.

## Hard rules

- Always include explicit `init:` on every new state var (`was_moving`, `done_pulse_left`, …).
- Retarget rule must clear `done_active`, `done_pulse_left`, AND TX `IsDone=false` — otherwise a retarget mid-pulse sticks the high window open.
- TX payload `done_pulse_left > 0` evaluates to bool; codegen wraps with `_net(...)`
  to native `bool` for restbus.
- Rule order on same timer is load-bearing: think **read-then-write**, **publish-then-decay**,
  **arm-then-publish**.
- Pulse width budget × timer interval must be ≥ 4 × DBC `GenMsgCycleTime` of the
  receiver's frame, otherwise tests miss the high window.
- A pulse end must include TX `false` (one-shot) — otherwise the high stays sticky.

## Anti-patterns

- Setting `IsDone` directly from `update_moving` (becomes sticky level, not pulse).
- Reading pulse status by comparing elapsed time across rules (use a budget counter).
- Sharing rule logic between handler and ticker — keep on_rx and on_timer rules
  physically separate; one shared rule can't fire on both.

## See also

- `02-subdomains.md` → "On same timer: service order"
- `03-field-graph.md` → edge memory + pulse sub-graphs
- Golden example: [`examples/door_ecu.min.yaml`](examples/door_ecu.min.yaml),
  [`examples/seat_ecu.min.yaml`](examples/seat_ecu.min.yaml)
