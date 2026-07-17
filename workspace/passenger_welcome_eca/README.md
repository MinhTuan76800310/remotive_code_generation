# Passenger Welcome — ECA generator workspace

Working tree for the **new** bmgen front-end that consumes `schema_Nhan`-style ECU YAML
and emits Remotive Behavioral Model Python.

## Scenario: Passenger Welcome

Full signal map (draw.io + SVG):

- [`passenger_welcome_signal_map.drawio`](./passenger_welcome_signal_map.drawio)
- [`passenger_welcome_signal_map.svg`](./passenger_welcome_signal_map.svg)

```mermaid
flowchart LR
  Tester["Tester / HMI"]
  Door["DoorECU"]
  HPC["CentralHPC"]
  Seat["SeatECU"]
  Light["LightControlECU"]
  Bus["Bus / observers"]

  Tester -->|"DoorCommand.DoorOpenRequest"| Door
  Door -->|"DoorStatus.DoorOpenDone"| HPC
  HPC -->|"SeatCommand.SeatAdjustRequest"| Seat
  Seat -->|"SeatStatus.SeatAdjustDone"| HPC
  Seat -.->|"SeatStatus.SeatPosition"| Bus
  HPC -->|"LightCommand.AmbientLightRequest"| Light
  Light -->|"LightStatus.AmbientLightDone"| HPC
  Light -.->|"AmbientScene / AmbientBrightness"| Bus
  HPC -->|"WelcomeStatus.WelcomeComplete"| Bus
```

| ECU | Role |
|-----|------|
| **DoorECU** | Receive door-open request → run open sequence → report done to CentralHPC |
| **CentralHPC** | On door open → fan-out seat adjust + ambient light → wait both done → end welcome |
| **SeatECU** | Receive seat adjust request → apply driver-context position → report done |
| **LightControlECU** | Receive ambient light request → apply welcome config → report done |

## Layout

```text
passenger_welcome_eca/
  README.md
  schema/                 # schema_Nhan dialect reference (symlink or copy)
  examples/               # 4 ECU YAML for this scenario
    SPECS.md              # per-ECU behavior spec
    door_ecu.yaml
    central_hpc.yaml
    seat_ecu.yaml
    light_control_ecu.yaml
```

Per-ECU specs (interfaces, params, state, timers, rules, acceptance):
[`examples/SPECS.md`](./examples/SPECS.md).

## Dialect

See repo root [`docs/schema_Nhan.yaml`](../../docs/schema_Nhan.yaml) and behavior spec
[`docs/schema_Nhan_bmgen_behavior.md`](../../docs/schema_Nhan_bmgen_behavior.md).

Signal names use `Frame.Signal` so a future Remotive binding can map FrameFilter cleanly.
Cross-ECU coordination is **signal-level only** (no topology file in this workspace yet).

## Signal map

| From → To | Signal | Meaning |
|-----------|--------|---------|
| (tester/HMI) → DoorECU | `DoorCommand.DoorOpenRequest` | request open (~1.5s if closed; ack ngay if open) |
| (tester/HMI) → DoorECU | `DoorCommand.DoorCloseRequest` | request close (~1.5s if open; ack ngay if closed) |
| DoorECU → CentralHPC | `DoorStatus.DoorOpenDone` | door open complete |
| DoorECU → bus | `DoorStatus.DoorCloseDone` | door close complete |
| CentralHPC → SeatECU | `SeatCommand.SeatAdjustRequest` | profile id |
| SeatECU → CentralHPC | `SeatStatus.SeatAdjustDone` | seat done |
| SeatECU → bus | `SeatStatus.SeatPosition` | position mm |
| CentralHPC → LightControlECU | `LightCommand.AmbientLightRequest` | scene id |
| LightControlECU → CentralHPC | `LightStatus.AmbientLightDone` | light done |
| LightControlECU → bus | `LightStatus.AmbientBrightness` / `AmbientScene` | applied config |
| CentralHPC → bus | `WelcomeStatus.WelcomeComplete` | sequence end |

## Schema gap used as pattern

`actions` only allow `tx | set_state` — no `start_timer`. Actuator ECUs therefore use
`timers.auto_start: true` and gate completion rules with state (`$door_opening`,
`$adjusting`, `$lighting`). First tick after request latches complete (interval ≈ sequence duration).

## Live E2E (Remotive)

Four example YAMLs generate pure bmgen-eca models and run together on a dedicated
topology (does **not** modify `getting_started`):

`test_env/remotivelabs-topology-examples/passenger_welcome/`

```bash
# schema_v2 examples → generate ×4 → pure-copy → topology → pytest golden path
bash test_env/remotivelabs-topology-examples/passenger_welcome/scripts/run_passenger_welcome_ui.sh test-only all
```

Golden path: Door `TargetPosition=100` → Central edge on `DoorStatus.IsDone` →
fan-out seat target `5` + ambient `1` → join → `WelcomeStatus.WelcomeComplete=1`.

Buses (zero-patch `CanNamespace`): `DoorECU-BodyCan0`, `SeatECU-BodyCan0`,
`LightControlECU-BodyCan0`, `CentralHPC-BodyCan0` on one physical `BodyCan0`.

Compiler package: monorepo `bmgen_ECA/` (`python -m bmgen_eca generate …`).
