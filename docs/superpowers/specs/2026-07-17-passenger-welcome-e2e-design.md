# Passenger Welcome multi-ECU Remotive E2E — Design

**Date:** 2026-07-17  
**Status:** approved (brainstorm)  
**Approach:** Pure bmgen-eca ladder (Approach 1)  
**Host:** new topology `passenger_welcome/` (does not modify `getting_started`)

---

## 1. Problem

Four schema_v2 ECU YAMLs for Passenger Welcome already parse green under `bmgen_ECA`:

| ECU | File | Live today? |
|-----|------|-------------|
| DoorECU | `examples/door_ecu.yaml` | Yes — `getting_started` pure-copy E2E |
| SeatECU | `examples/seat_ecu.yaml` | No |
| LightControlECU | `examples/light_control_ecu.yaml` | No |
| CentralHPC | `examples/central_hpc.yaml` | No |

They do **not** yet run together on Remotive. Gaps:

1. **Bus strings inconsistent** — Door uses `DoorECU-BodyCan0`; Seat `SE-BodyCAN`; Light `LCE-BodyCAN`; Central workaround `BodyCAN` (comment claimed multi-bus block).
2. **No shared topology** for all four + DBC frames for seat position/IsDone, ambient, WelcomeComplete.
3. **Central** ends welcome by clearing `welcome_active` only — no bus-visible `WelcomeComplete` yet.
4. Misconception risk: multi-namespace codegen looked required; **verified not** on shared physical channel.

### Remotive routing (verified)

On `getting_started` / VF-style shared channel:

- Each ECU binds **one** `CanNamespace("{ecu}-{channel}")`.
- Tester publishes on commander NS (e.g. `DOOR_CTRL-BodyCan0`); model subscribes on **own** NS and still receives peer frames.
- Evidence: Door E2E 6/6; `interfaces.json` all chains share `can_physical_channel_name: BodyCan0` + UDP multicast; VF platform comment: *all nodes see all frames*.

**Implication:** compiler multi-bus (`E_MULTI_BUS_UNSUPPORTED`) is **not** a blocker for this scenario. Each YAML keeps a **single** bus token equal to that ECU’s Remotive namespace.

---

## 2. Goals / non-goals

### Goals

1. Full Passenger Welcome on Remotive: Door → Central fan-out → Seat + Light join → **WelcomeComplete**.
2. All four models = **pure** `bmgen-eca generate` output (md5 pure-copy, no hand logic edits).
3. Zero-patch namespaces: YAML bus = `{ecu_mock.name}-BodyCan0`.
4. One golden-path E2E pytest + run script (generate ×4 → topology → compose → test).
5. New topology tree so `getting_started` Door/Seat proofs stay untouched.

### Non-goals

- Multi-bus compiler / multi-physical-channel codegen.
- Migrating or replacing `getting_started` Door/Seat stacks.
- SPECS abstract dialect (`DoorOpenRequest` / fade timers) — live YAMLs use TargetPosition / IsDone / AmbientReq as authored.
- Full negative matrix / per-ECU acceptance from SPECS.md.
- Dual-repo product push until E2E green (implementation plan may stage commits).

---

## 3. Decisions (from brainstorm)

| Topic | Choice |
|-------|--------|
| Scope | Full 4 ECU welcome |
| Bus model | One physical `BodyCan0`; one NS per ECU |
| ECU names | Match YAML: `DoorECU`, `SeatECU`, `LightControlECU`, `CentralHPC` |
| Proof | Golden path + TX `WelcomeStatus.WelcomeComplete` |
| Topology host | New `passenger_welcome/` |
| Approach | Pure bmgen ladder (not hybrid Central, not tester-orchestrated) |

---

## 4. Architecture

```text
                    BodyCan0 (1 DBC, UDP multicast)
   ┌────────────┐   ┌──────────────┐   ┌──────────────────┐   ┌─────────────┐
   │  DoorECU   │   │   SeatECU    │   │ LightControlECU  │   │ CentralHPC  │
   │ *-BodyCan0 │   │ *-BodyCan0   │   │ *-BodyCan0       │   │ *-BodyCan0  │
   └─────▲──────┘   └──────▲───────┘   └────────▲─────────┘   └──────▲──────┘
         │                 │                     │                    │
   DoorCmd / DoorStatus    PW_SeatCmd/Status     AmbientCmd/Light     WelcomeStatus
         │                 │                     │                    │
   DOOR_CTRL mock          Central TX            Central TX           tester observe
```

### Golden path (nominal, current YAML params)

```text
t≈0     Tester → DoorCmd.TargetPosition = 100  (DOOR_CTRL-BodyCan0)
t≈2s    Door: CurrentPosition→100, IsDone 0→1
        Central: false→true edge on DoorStatus.IsDone
                → welcome_active; TX SeatPosTarget=5, AmbientReq=1
t≈2s+   Light: AmbientLight→1 (1:1 mirror; skip if same)
t≈2s+2s Seat: 20×0.1s startup then step ±1 to 5; IsDone=1
        Central: seat_done ∧ light_done → welcome_active=false
                TX WelcomeComplete=1
```

### Namespace rule

| ECU | CanNamespace (YAML bus) |
|-----|-------------------------|
| DoorECU | `DoorECU-BodyCan0` |
| SeatECU | `SeatECU-BodyCan0` |
| LightControlECU | `LightControlECU-BodyCan0` |
| CentralHPC | `CentralHPC-BodyCan0` |
| DOOR_CTRL (mock) | `DOOR_CTRL-BodyCan0` (tester open only) |

Central RX/TX signal **names** match peer frames; bus prefix in YAML is **Central’s** NS only (not Door’s). Example:

```yaml
- signal: "[CentralHPC-BodyCan0]DoorStatus.IsDone"   # correct for Central
# NOT: "[DoorECU-BodyCan0]DoorStatus.IsDone" inside Central YAML
```

---

## 5. Components

### 5.1 YAML changes (`workspace/passenger_welcome_eca/examples/`)

| File | Change |
|------|--------|
| `door_ecu.yaml` | No bus change (already live shape) |
| `seat_ecu.yaml` | `SE-BodyCAN` → `SeatECU-BodyCan0` (all signal refs) |
| `light_control_ecu.yaml` | `LCE-BodyCAN` → `LightControlECU-BodyCan0` |
| `central_hpc.yaml` | `BodyCAN` → `CentralHPC-BodyCan0`; add `can_tx` + TX action `WelcomeStatus.WelcomeComplete=1` on both end-welcome rules |

Keep frame/signal leaf names as in current YAML (`PW_SeatCmd.SeatPosTarget`, `PW_SeatStatus.*`, `PW_AmbientLightCmd.AmbientReq`, `PW_AmbientLight.AmbientLight`, `DoorCmd` / `DoorStatus`).

Optional: keep `schema/schema_v2.yaml` as Door-only fixture for unit tests; examples/ are E2E sources.

### 5.2 DBC (new)

Path: `test_env/remotivelabs-topology-examples/passenger_welcome/platform/databases/body_can.dbc`

| BO_ | Sender | Key signals | Receivers (doc) |
|-----|--------|-------------|-----------------|
| DoorCmd | DOOR_CTRL | TargetPosition | DoorECU |
| DoorStatus | DoorECU | CurrentPosition, IsMoving, IsDone | CentralHPC, observers |
| PW_SeatCmd | CentralHPC | SeatPosTarget | SeatECU |
| PW_SeatStatus | SeatECU | SeatPosition, IsDone | CentralHPC |
| PW_AmbientLightCmd | CentralHPC | AmbientReq | LightControlECU |
| PW_AmbientLight | LightControlECU | AmbientLight | CentralHPC |
| WelcomeStatus | CentralHPC | WelcomeComplete | observers |

Rules: one sender per BO_; cyclic GenMsgCycleTime where restbus needs it (mirror Door 50 ms).

### 5.3 Topology layout

```text
passenger_welcome/
  platform/
    topology.platform.yaml      # BodyCan0 → body_can.dbc
    databases/body_can.dbc
  models/
    door_ecu/                   # pure copy
    seat_ecu/
    light_control_ecu/
    central_hpc/
    door_ecu.instance.yaml
    seat_ecu.instance.yaml
    light_control_ecu.instance.yaml
    central_hpc.instance.yaml
  instances/main.instance.yaml
  settings/can_over_udp.settings.instance.yaml
  tests/
    tester.instance.yaml        # DOOR_CTRL: mock: {}
    conftest.py
    test_passenger_welcome_e2e.py
  scripts/run_passenger_welcome_ui.sh
  pyproject.toml / Dockerfile   # numpy + models on PYTHONPATH
```

### 5.4 Generate pipeline

```text
for each examples/{door,seat,light,central}.yaml:
  bmgen-eca generate → workspace/.../_generated_<ecu>/
  pure-copy bmgen_generated/<pkg>/* → passenger_welcome/models/<pkg>/
  md5 check
remotive topology generate -f main -f settings
assert each ECU interfaces.json namespace == "{Name}-BodyCan0"
docker compose up / pytest
```

Package module names: snake from ECU (`DoorECU` → `door_ecu`, `LightControlECU` → `light_control_ecu`, `CentralHPC` → `central_hpc`, `SeatECU` → `seat_ecu`) — match existing bmgen_ECA `ecu_name` → package mapping.

---

## 6. Testing

### Static (optional)

- Four `__main__.py` present after copy.
- Each contains `CanNamespace("<Ecu>-BodyCan0")` and live keys `Frame.Signal` (no `[Bus]` prefix in signal dict keys).

### Runtime golden path (required)

| Step | Assert |
|------|--------|
| Ping | DoorECU, SeatECU, LightControlECU, CentralHPC, DOOR_CTRL |
| Open | set `DoorCmd.TargetPosition=100` on `DOOR_CTRL-BodyCan0` |
| Door | `CurrentPosition≈100`, `IsDone==1` (~5s) |
| Seat | `SeatPosition==5`, `IsDone==1` (~5s after fan-out) |
| Light | `AmbientLight==1` (~2s) |
| Join | `WelcomeStatus.WelcomeComplete==1` (~3s after both done) |

Observer NS: any BodyCan0 participant works; default **`DOOR_CTRL-BodyCan0`** (same pattern as door suite) or dedicated mock if capture needs isolation — implementation picks one that receives all frames on shared channel.

**WelcomeComplete:** TX level `1` on join; no auto-clear in MVP.

**pytest timeout:** ~20–30s for the case.

### Door edge caveat

Door `IsDone` is level (`current≈target`). At boot `current=target=0` → IsDone may already be 1. Golden path **must** command a move (e.g. 0→100) so Central sees false→true (or true→false→true). Central rule: `IsDone==true and prev_door_done==false`. If boot publishes IsDone=1 before Central latches prev, edge can be lost — mitigate by:

1. Command open after stack healthy (Central already running, prev latched from first frames), **or**
2. Ensure first observed IsDone for Central is 0 then 1 during travel.

Implementation must prove edge fires (log or assert seat/light commands after open).

---

## 7. Risks

| Risk | Mitigation |
|------|------------|
| IsDone boot edge miss | Open after healthy; assert fan-out side effects |
| Seat already at 5 / light already 1 | Central `*_already_at_target` rules on door edge |
| Numpy restbus types | Existing codegen `_net()` + set_state casts |
| `python -m <pkg>` import | PYTHONPATH=models or pyproject multi-package |
| DBC sender wrong | Central owns SeatCmd + AmbientCmd + WelcomeStatus |
| getting_started drift | Separate tree; no shared compose |

---

## 8. Out of scope

- Multi-bus compiler work
- `getting_started` rename SEAT→SeatECU
- SPECS.md abstract open/close request model
- Negative cases / full SPECS acceptance matrix
- Pulse-clear WelcomeComplete handshake
- RebootRequest control handlers

---

## 9. Teaching checklist

Human should be able to explain:

1. **Problem:** four parse-green YAMLs ≠ live multi-ECU welcome.
2. **Why shared channel works:** own-NS subscribe still sees peer TX on BodyCan0.
3. **Why no multi-bus compiler:** one bus token per YAML = that ECU’s namespace.
4. **Why Central bus ≠ Door bus string:** bus in YAML names **local** CanNamespace; frame names carry identity.
5. **Why pure-copy:** md5; logic only in YAML + codegen.
6. **Why WelcomeComplete:** bus-visible join; `welcome_active` alone is internal.
7. **Why new topology:** isolate from Door-only / Seat-legacy getting_started proofs.
8. **Door IsDone edge:** level status needs a real move for false→true.

---

## 10. Success criteria

1. `bash .../run_passenger_welcome_ui.sh test-only all` (or equivalent) green.
2. Zero hand edits to generated `__main__.py` after generate (md5).
3. `interfaces.json` namespaces match YAML buses without patch scripts.
4. Golden path observes Door done → seat+light → WelcomeComplete=1.

---

## 11. Implementation order (preview; plan skill expands)

1. Rewrite 4 YAML buses + Central WelcomeComplete; parse green.
2. Scaffold `passenger_welcome/` platform + DBC + instances + packaging.
3. Generate ×4 pure-copy into models.
4. Topology generate; namespace asserts.
5. E2E test + run script.
6. Run golden path; fix only YAML/DBC/codegen if needed (not hand model).
7. Commit monorepo paths; optional dual-push bmgen_ECA only if compiler touched (expected: no).
