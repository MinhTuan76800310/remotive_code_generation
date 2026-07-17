# Passenger Welcome — per-component test suite work log

> Skill seed: how we designed, what failed, what fixed it.
> Date: 2026-07-17

## Goal

Thorough **per-component** live tests (Door / Seat / Light / Central), door-style edge cases,
run via `run_passenger_welcome_ui.sh test …` against a **kept-up** stack (no generate/down).

## Constraints (user)

1. Containers stay up — only signals change.
2. Mirror door test style (static + runtime + edges).
3. Log process for skill extraction.

## Topology facts (discovered / re-verified)

| Fact | Evidence |
|------|----------|
| Shared physical `BodyCan0` via UDP multicast | `interfaces.json` all chains `can_physical_channel_name=BodyCan0` |
| Observer NS for tests | `DOOR_CTRL-BodyCan0` (mock) |
| Door inject NS | `DOOR_CTRL-BodyCan0:DoorCmd.TargetPosition` (DBC sender DOOR_CTRL) |
| SeatCmd / AmbientCmd DBC sender | **CentralHPC** (not DOOR_CTRL) |
| Central owns restbus after first welcome | model TX `PW_SeatCmd` / `PW_AmbientLightCmd` on start_welcome |
| Boot auto-welcome | Door init `IsDone=true` at 0 → Central edge → SeatCmd=5 sticky |

## Isolation strategy (chosen)

| Component | Drive path | Why |
|-----------|------------|-----|
| **Door** | `DOOR_CTRL` restbus `DoorCmd` | DBC owner; no conflict |
| **Seat** | Hijack `CentralHPC-BodyCan0:PW_SeatCmd.SeatPosTarget` | DBC+runtime owner; DOOR_CTRL inject loses to Central cycle |
| **Light** | Hijack `CentralHPC-BodyCan0:PW_AmbientLightCmd.AmbientReq` | same |
| **Central** | Door open edge only | exercises coordinator; no direct state API |

**Never** `restbus reset` on model namespaces (`DoorECU-*`, `SeatECU-*`, `CentralHPC-*`, …) —
that kills model TX and breaks golden path until force-recreate.

Safe: reset/add only on `DOOR_CTRL-BodyCan0` for DoorCmd (or leave as-is).

## Failures → fixes

| # | Failure | Root cause | Fix |
|---|---------|------------|-----|
| 1 | Seat inject via DOOR_CTRL never moves | Central restbus keeps SeatCmd=5 after welcome | Hijack **CentralHPC** NS values |
| 2 | Light inject flaky | Competing DOOR_CTRL AmbientCmd restbus | Do not add AmbientCmd on DOOR_CTRL; only Central |
| 3 | After `restbus reset CentralHPC` golden breaks | Model restbus config wiped | Never reset model NS; force-recreate if needed |
| 4 | Seat reaches pos but IsDone match fails | Same-tick / capture timing | Wait pos first, then IsDone; or combined after settle |
| 5 | Fresh stack SeatCmd not on bus | restbus frame not registered | Central creates on welcome; or CLI `restbus add` on Central after model up |
| 6 | `update_signals` alone without prior restbus owner | No cyclic TX | Prefer hijack after boot welcome (always happens) |

## Case matrix (target)

### DoorECU (`test_door_component.py`)
- static: model exists, Frame.Signal keys, NS DoorECU-BodyCan0, IsDone TX
- runtime: 0→50 stop; 50→100; clamp 150→100; mid 36; IsMoving while travel; return 0 IsDone; re-open after close

### SeatECU (`test_seat_component.py`)
- static: keys, NS, startup_ticks=20, move_step=1
- runtime (via Central hijack): move to N + IsDone; retarget clears IsDone then arrives; same-target no regress; multi-step 0→10 timing; IsDone sticky at target

### LightControlECU (`test_light_component.py`)
- static: keys, NS, boot AmbientLight
- runtime: set AmbientReq→AmbientLight 1:1; change value; (optional) same-value skip is hard to assert on sticky restbus — assert level after distinct values only

### CentralHPC (`test_central_component.py`)
- static: WelcomeComplete clear+set, welcome_seat_pos=5, welcome_ambient=1
- runtime: golden open; second cycle; mid door 50; clamp door 150; WelcomeComplete after seat+light join

### Integration (existing `test_passenger_welcome_bmgen.py`)
- keep golden suite; run after component suites

## Run contract

```bash
# once
bash .../run_passenger_welcome_ui.sh up

# many times — no down
bash .../run_passenger_welcome_ui.sh test door
bash .../run_passenger_welcome_ui.sh test seat
bash .../run_passenger_welcome_ui.sh test light
bash .../run_passenger_welcome_ui.sh test central
bash .../run_passenger_welcome_ui.sh test all   # integration + components
```

## Skill notes (for later)

1. Shared-bus multi-ECU tests: inject on **DBC sender NS**, observe on mock NS.
2. Coordinator-owned commands cannot be freely injected from mock without hijacking owner restbus.
3. Boot edge on level `IsDone` means stack is never “idle” after models start — design tests around sticky welcome params or explicit settle.
4. Never wipe model restbus; recover with container recreate only.
5. Door-style suite structure: static pure-copy → helpers → runtime edges → timeouts from YAML params.

## Results (2026-07-17 live, stack kept up)

| Suite | Result | Wall |
|-------|--------|------|
| `test door` | 10/10 | ~27s |
| `test seat` | 8/8 | ~17s |
| `test light` | 7/7 | ~1.4s |
| `test central` | 8/8 | ~31s |
| `test integ` | 9/9 | ~37s |
| **Total** | **42/42** | — |

Containers after all suites: door/seat/light/central/web-app still **Up** (no down).

## Files added

- `passenger_welcome/tests/_bus.py` — shared OBS/OWN helpers
- `passenger_welcome/tests/test_door_component.py`
- `passenger_welcome/tests/test_seat_component.py`
- `passenger_welcome/tests/test_light_component.py`
- `passenger_welcome/tests/test_central_component.py`
- `scripts/run_passenger_welcome_ui.sh` — suite aliases `door|seat|light|central|components|integ|all`
- this worklog
