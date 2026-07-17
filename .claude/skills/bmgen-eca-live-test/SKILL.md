---
name: bmgen-eca-live-test
description: >-
  Write or extend live Remotive E2E tests for pure bmgen-eca multi-ECU stacks
  (Passenger Welcome style). Use when the user asks for component tests, per-ECU
  edge cases, keep-stack-up pytest, restbus inject isolation, seat/light/central
  suites, or run_passenger_welcome_ui.sh test door|seat|light|central. Also for
  debugging flaky WelcomeComplete / SeatCmd inject failures.
---

# bmgen-eca-live-test

Live proof for **pure-copy** bmgen-eca models on a Remotive topology.
Containers stay up; tests only change signals and assert.

## Before writing tests

Read (relative to this skill):

1. `references/00-topology-facts.md`
2. `references/01-isolation-strategy.md`
3. `references/02-suite-layout.md`
4. On flake / inject fail: `references/03-failures-and-fixes.md`
5. Run CLI contract: `references/04-run-contract.md`

## Workflow

1. Confirm stack is **up** (`run_*.sh up` once). Do **not** `down` after tests.
2. Identify each ECU's **DBC sender** for its command frames (not always the mock).
3. Add/extend helpers in `tests/_bus.py` (OBS mock NS + OWN for hijacked cmds).
4. Per component file: **static pure-copy** first, then **runtime edges**.
5. Timeouts from YAML params (step, tick, startup_ticks) + margin.
6. Wire suite alias in run script: `test door|seat|light|central|components|integ|all`.
7. Run against live stack; report pass counts. Stack must still be Up.

## Hard rules

| Do | Don't |
|----|-------|
| Inject on **DBC / runtime restbus owner** NS | Assume DOOR_CTRL can drive every frame |
| Observe on mock NS (`DOOR_CTRL-BodyCan0`) | `restbus reset` on model NS (`*ECU-*`, `CentralHPC-*`) |
| Hijack coordinator restbus for SeatCmd/AmbientCmd | Stop containers to "isolate" (unless full recreate) |
| Settle via signals (door→0) | Auto-down after pytest |
| Static assert `Frame.Signal` keys + zero-patch NS | Hand-edit generated `__main__.py` |

## DONE definition

- Component suite(s) green on live broker.
- ECU containers still **Up** after run.
- No model-namespace restbus reset used in the path that passed.

## Reference topology (Passenger Welcome)

```text
test_env/remotivelabs-topology-examples/passenger_welcome/
  scripts/run_passenger_welcome_ui.sh
  tests/_bus.py
  tests/test_*_component.py
  tests/test_passenger_welcome_bmgen.py
```
