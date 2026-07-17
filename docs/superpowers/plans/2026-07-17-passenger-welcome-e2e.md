# Passenger Welcome multi-ECU Remotive E2E Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run pure bmgen-eca Door + Seat + Light + CentralHPC together on a new Remotive `passenger_welcome` topology and prove golden-path WelcomeComplete.

**Architecture:** One physical `BodyCan0` (shared DBC, UDP multicast). Each ECU YAML uses a single bus token `{ecu_mock.name}-BodyCan0` so codegen emits one `CanNamespace` per model (zero-patch). Models are pure-copied from `bmgen-eca generate`. Tester opens the door via mock `DOOR_CTRL`; Central fans out seat/light and TX `WelcomeStatus.WelcomeComplete`.

**Tech Stack:** schema_v2 / `bmgen_ECA`, Remotive Topology 0.17+, Docker Compose, pytest-asyncio, numpy (codegen), DBC.

**Spec:** [docs/superpowers/specs/2026-07-17-passenger-welcome-e2e-design.md](../specs/2026-07-17-passenger-welcome-e2e-design.md)

## Global Constraints

- Pure-copy only: never hand-edit generated `__main__.py` logic; fix YAML or codegen instead.
- No multi-bus compiler work; each YAML has exactly one bus string.
- Do **not** modify `getting_started` models/tests/scripts for this feature.
- ECU Remotive names = YAML `ecu_mock.name`: `DoorECU`, `SeatECU`, `LightControlECU`, `CentralHPC`.
- Package dirs from `snake_case(ecu_name)`: `door_ecu`, `seat_ecu`, `light_control_ecu`, `central_hpc`.
- Namespace strings: `DoorECU-BodyCan0`, `SeatECU-BodyCan0`, `LightControlECU-BodyCan0`, `CentralHPC-BodyCan0`, `DOOR_CTRL-BodyCan0`.
- Nested git: `test_env/remotivelabs-topology-examples/` is its own repo; monorepo commits cover `workspace/` + `docs/`; topology tree commits (or stays local) under that nested repo as appropriate.
- `bmgen-eca` via `PYTHONPATH=bmgen_ECA/src` or installed editable; prefer `python3 -m bmgen_eca` if CLI missing.

## File map

| Path | Role |
|------|------|
| `workspace/passenger_welcome_eca/examples/{door,seat,light_control,central_hpc}_ecu.yaml` / `central_hpc.yaml` | Sources of truth (bus rename + WelcomeComplete) |
| `test_env/remotivelabs-topology-examples/passenger_welcome/**` | New topology (platform, DBC, models, instances, tests, script) |
| `docs/superpowers/specs/2026-07-17-passenger-welcome-e2e-design.md` | Spec (already committed) |
| Codegen | **No change expected** |

---

### Task 1: Align four example YAMLs + WelcomeComplete

**Files:**
- Modify: `workspace/passenger_welcome_eca/examples/seat_ecu.yaml` (all `SE-BodyCAN` → `SeatECU-BodyCan0`)
- Modify: `workspace/passenger_welcome_eca/examples/light_control_ecu.yaml` (all `LCE-BodyCAN` → `LightControlECU-BodyCan0`)
- Modify: `workspace/passenger_welcome_eca/examples/central_hpc.yaml` (`BodyCAN` → `CentralHPC-BodyCan0`; add WelcomeComplete TX)
- Keep: `workspace/passenger_welcome_eca/examples/door_ecu.yaml` (already `DoorECU-BodyCan0`)
- Test: parse via `python3 -m bmgen_eca parse`

**Interfaces:**
- Consumes: existing schema_v2 dialect
- Produces: four parse-green YAMLs with zero-patch bus strings; Central TX `WelcomeStatus.WelcomeComplete`

- [ ] **Step 1: Rewrite seat bus strings**

In `seat_ecu.yaml`, replace every `[SE-BodyCAN]` with `[SeatECU-BodyCan0]` (interfaces + rule targets + payloads). Resulting RX/TX:

```yaml
can_rx:
  - signal: "[SeatECU-BodyCan0]PW_SeatCmd.SeatPosTarget"
can_tx:
  - signal: "[SeatECU-BodyCan0]PW_SeatStatus.SeatPosition"
  - signal: "[SeatECU-BodyCan0]PW_SeatStatus.IsDone"
```

- [ ] **Step 2: Rewrite light bus strings**

In `light_control_ecu.yaml`, replace every `[LCE-BodyCAN]` with `[LightControlECU-BodyCan0]`.

- [ ] **Step 3: Rewrite Central bus + WelcomeComplete**

In `central_hpc.yaml`:

1. Replace every `[BodyCAN]` with `[CentralHPC-BodyCan0]`.
2. Add to `can_tx`:

```yaml
      - signal: "[CentralHPC-BodyCan0]WelcomeStatus.WelcomeComplete"
```

3. On **each** of these rules, append TX after clearing `welcome_active`:
   - `end_welcome_after_door_start`
   - `end_welcome_after_seat`
   - `end_welcome_after_light`

```yaml
        - type: set_state
          target: welcome_active
          payload: "false"
        - type: tx
          target: "[CentralHPC-BodyCan0]WelcomeStatus.WelcomeComplete"
          payload: "1"
```

4. Update the file header comment: remove “blocked by E_MULTI_BUS” multi-bus intended list; note single-NS shared-channel model.

- [ ] **Step 4: Parse all four**

```bash
export PYTHONPATH="/home/minhtuan958/Desktop/tuan_dz/code_generation/bmgen_ECA/src:${PYTHONPATH:-}"
EX=/home/minhtuan958/Desktop/tuan_dz/code_generation/workspace/passenger_welcome_eca/examples
for f in door_ecu.yaml seat_ecu.yaml light_control_ecu.yaml central_hpc.yaml; do
  echo "=== $f ==="
  python3 -m bmgen_eca parse "$EX/$f"
done
```

Expected: each prints `ok` (0 errors; warnings OK only if documented unused).

- [ ] **Step 5: Spot-check generate namespaces**

```bash
OUT=/tmp/pw_yaml_check
rm -rf "$OUT" && mkdir -p "$OUT"
for f in door_ecu seat_ecu light_control_ecu central_hpc; do
  python3 -m bmgen_eca generate "$EX/${f}.yaml" --out "$OUT/$f"
done
# package dirs
ls "$OUT/door_ecu/bmgen_generated/"   # door_ecu
ls "$OUT/seat_ecu/bmgen_generated/"   # seat_ecu
ls "$OUT/light_control_ecu/bmgen_generated/"  # light_control_ecu
ls "$OUT/central_hpc/bmgen_generated/"       # central_hpc
# namespace strings in main
grep -n 'CanNamespace' \
  "$OUT/door_ecu/bmgen_generated/door_ecu/__main__.py" \
  "$OUT/seat_ecu/bmgen_generated/seat_ecu/__main__.py" \
  "$OUT/light_control_ecu/bmgen_generated/light_control_ecu/__main__.py" \
  "$OUT/central_hpc/bmgen_generated/central_hpc/__main__.py"
grep -n 'WelcomeStatus.WelcomeComplete\|_
  "$OUT/central_hpc/bmgen_generated/central_hpc/__main__.py"
```

Expected: `CanNamespace("DoorECU-BodyCan0"…)` etc.; Central contains `WelcomeStatus.WelcomeComplete` and `_net(` on TX values.

- [ ] **Step 6: Commit (monorepo)**

```bash
cd /home/minhtuan958/Desktop/tuan_dz/code_generation
git add workspace/passenger_welcome_eca/examples/seat_ecu.yaml \
        workspace/passenger_welcome_eca/examples/light_control_ecu.yaml \
        workspace/passenger_welcome_eca/examples/central_hpc.yaml
git commit -m "feat(pw): align ECU YAML buses + Central WelcomeComplete"
```

---

### Task 2: Scaffold `passenger_welcome` topology (platform, DBC, packaging)

**Files:**
- Create: `test_env/remotivelabs-topology-examples/passenger_welcome/platform/topology.platform.yaml`
- Create: `test_env/remotivelabs-topology-examples/passenger_welcome/platform/databases/body_can.dbc`
- Create: `test_env/remotivelabs-topology-examples/passenger_welcome/settings/can_over_udp.settings.instance.yaml`
- Create: `test_env/remotivelabs-topology-examples/passenger_welcome/instances/main.instance.yaml`
- Create: `test_env/remotivelabs-topology-examples/passenger_welcome/models/{door,seat,light_control,central_hpc}_ecu.instance.yaml` (note: central = `central_hpc.instance.yaml`)
- Create: `test_env/remotivelabs-topology-examples/passenger_welcome/tests/tester.instance.yaml`
- Create: `test_env/remotivelabs-topology-examples/passenger_welcome/pyproject.toml`
- Create: `test_env/remotivelabs-topology-examples/passenger_welcome/Dockerfile`
- Create: `test_env/remotivelabs-topology-examples/passenger_welcome/README.md` (short)
- Copy: `LICENSE` from getting_started if required by Docker build
- Create stub: `models/{door_ecu,seat_ecu,light_control_ecu,central_hpc}/__init__.py` (empty) so tree exists before generate

**Interfaces:**
- Consumes: Remotive instance schema 0.17; DBC senders matching §5.2 of design
- Produces: `remotive topology generate` succeeds after models exist (Task 3 fills packages)

- [ ] **Step 1: Platform + settings**

`platform/topology.platform.yaml`:

```yaml
schema: remotive-topology-platform:0.17
channels:
  BodyCan0:
    type: can
    database: ./databases/body_can.dbc
    can_physical_channel_name: BodyCan0
```

`settings/can_over_udp.settings.instance.yaml`:

```yaml
schema: remotive-topology-instance:0.17
settings:
  can:
    default_driver: udp
```

- [ ] **Step 2: Write DBC**

`platform/databases/body_can.dbc` — full content:

```
VERSION "1.0"

NS_ :
    BO_
    SG_
    BA_DEF_
    BA_
    VAL_
    BU_

BU_:
    DoorECU
    DOOR_CTRL
    SeatECU
    LightControlECU
    CentralHPC

BO_ 300 DoorCmd: 1 DOOR_CTRL
 SG_ TargetPosition : 0|8@1+ (1,0) [0|100] "" DoorECU

BO_ 301 DoorStatus: 2 DoorECU
 SG_ CurrentPosition : 0|8@1+ (1,0) [0|100] "" CentralHPC
 SG_ IsMoving : 8|1@1+ (1,0) [0|1] "" CentralHPC
 SG_ IsDone : 9|1@1+ (1,0) [0|1] "" CentralHPC

BO_ 200 PW_SeatCmd: 1 CentralHPC
 SG_ SeatPosTarget : 0|8@1+ (1,0) [0|100] "" SeatECU

BO_ 201 PW_SeatStatus: 2 SeatECU
 SG_ SeatPosition : 0|8@1+ (1,0) [0|100] "" CentralHPC
 SG_ IsDone : 8|1@1+ (1,0) [0|1] "" CentralHPC

BO_ 400 PW_AmbientLightCmd: 1 CentralHPC
 SG_ AmbientReq : 0|8@1+ (1,0) [0|255] "" LightControlECU

BO_ 401 PW_AmbientLight: 1 LightControlECU
 SG_ AmbientLight : 0|8@1+ (1,0) [0|255] "" CentralHPC

BO_ 500 WelcomeStatus: 1 CentralHPC
 SG_ WelcomeComplete : 0|1@1+ (1,0) [0|1] "" DOOR_CTRL

VAL_ 300 TargetPosition 0 "Pos0" 50 "Pos50" 100 "Pos100";
VAL_ 301 IsMoving 0 "Idle" 1 "Moving";
VAL_ 301 IsDone 0 "Busy" 1 "Done";
VAL_ 201 IsDone 0 "Busy" 1 "Done";
VAL_ 500 WelcomeComplete 0 "Idle" 1 "Complete";

BA_DEF_ BO_ "GenMsgCycleTime" FLOAT 0 10000;

BA_ "GenMsgCycleTime" BO_ 300 50;
BA_ "GenMsgCycleTime" BO_ 301 50;
BA_ "GenMsgCycleTime" BO_ 200 50;
BA_ "GenMsgCycleTime" BO_ 201 50;
BA_ "GenMsgCycleTime" BO_ 400 50;
BA_ "GenMsgCycleTime" BO_ 401 50;
BA_ "GenMsgCycleTime" BO_ 500 50;
```

- [ ] **Step 3: Instance YAMLs**

`models/door_ecu.instance.yaml`:

```yaml
schema: remotive-topology-instance:0.17
ecus:
  DoorECU:
    models:
      door_ecu:
        type: container
        container:
          build:
            dockerfile: ../Dockerfile
          command: python -m door_ecu
```

`models/seat_ecu.instance.yaml` → ECU `SeatECU`, command `python -m seat_ecu`.  
`models/light_control_ecu.instance.yaml` → ECU `LightControlECU`, command `python -m light_control_ecu`.  
`models/central_hpc.instance.yaml` → ECU `CentralHPC`, command `python -m central_hpc`.

`instances/main.instance.yaml`:

```yaml
schema: remotive-topology-instance:0.17
name: passenger-welcome
platform:
  includes:
    - ../platform/topology.platform.yaml
includes:
  - ../models/door_ecu.instance.yaml
  - ../models/seat_ecu.instance.yaml
  - ../models/light_control_ecu.instance.yaml
  - ../models/central_hpc.instance.yaml
  - ../tests/tester.instance.yaml
```

`tests/tester.instance.yaml`:

```yaml
schema: remotive-topology-instance:0.17
containers:
  tester:
    profiles: [tester]
    build:
      dockerfile: ../Dockerfile
    volumes:
      - .:/app
    working_dir: /app
    command: "pytest --broker_url=http://topology-broker.com:50051 -s -vv"
    depends_on:
      - DOOR_CTRL-broker.com
      - DoorECU-broker.com
      - SeatECU-broker.com
      - LightControlECU-broker.com
      - CentralHPC-broker.com
ecus:
  DOOR_CTRL:
    mock: {}
```

- [ ] **Step 4: pyproject + Dockerfile**

Copy structure from `getting_started/pyproject.toml` with:

- `name = "remotivelabs-topology-passenger-welcome"`
- same deps including `numpy>=1.26`
- `module-root = "models"`, `module-name = "door_ecu"` (uv installs one package; others via PYTHONPATH)

Dockerfile = copy from getting_started, keep:

```dockerfile
ENV PYTHONPATH="/models:${PYTHONPATH}"
```

Copy `LICENSE` from getting_started into `passenger_welcome/`. Minimal `README.md` one paragraph + pointer to run script.

- [ ] **Step 5: Stub model packages**

```bash
PW=test_env/remotivelabs-topology-examples/passenger_welcome
for p in door_ecu seat_ecu light_control_ecu central_hpc; do
  mkdir -p "$PW/models/$p"
  echo '"""Pure bmgen-eca package; filled by run script."""' > "$PW/models/$p/__init__.py"
done
```

- [ ] **Step 6: uv lock (if uv available)**

```bash
cd test_env/remotivelabs-topology-examples/passenger_welcome
cp ../getting_started/uv.lock . 2>/dev/null || true
# Prefer regenerate:
uv lock
```

If lock fails, copy getting_started `uv.lock` and adjust name only if Docker build requires lock match — follow getting_started’s working pattern.

- [ ] **Step 7: Commit under nested topology repo if tracked**

```bash
cd test_env/remotivelabs-topology-examples
git status --short passenger_welcome | head
# if nested repo accepts:
git add passenger_welcome
git commit -m "feat(pw): scaffold passenger_welcome topology + DBC"
```

If nested repo policy is “local only”, leave uncommitted and note in monorepo worklog.

---

### Task 3: Generate pure-copy models + topology generate smoke

**Files:**
- Write (generated): `passenger_welcome/models/{door_ecu,seat_ecu,light_control_ecu,central_hpc}/{__init__,__main__}.py`
- Create: `passenger_welcome/scripts/run_passenger_welcome_ui.sh` (generate+copy+topology subset first; full test later)

**Interfaces:**
- Consumes: Task 1 YAMLs; Task 2 scaffold
- Produces: four pure models; `build/passenger_welcome/docker-compose.yml`; namespace asserts green

- [ ] **Step 1: Write run script core (generate + copy + topology)**

Create `scripts/run_passenger_welcome_ui.sh` executable. Mirror door script paths but:

```bash
REPO_ROOT=...   # resolve like door script: passenger_welcome → topo examples → test_env → monorepo
EXAMPLES="$REPO_ROOT/workspace/passenger_welcome_eca/examples"
GEN_ROOT="$REPO_ROOT/workspace/passenger_welcome_eca/_generated_pw"
PW_DIR=...      # passenger_welcome root

declare -A YAML_FOR=(
  [door_ecu]=door_ecu.yaml
  [seat_ecu]=seat_ecu.yaml
  [light_control_ecu]=light_control_ecu.yaml
  [central_hpc]=central_hpc.yaml
)

# for each package:
#   bmgen-eca generate "$EXAMPLES/${YAML}" --out "$GEN_ROOT/$pkg"
#   cp bmgen_generated/$pkg/{__init__,__main__}.py → models/$pkg/
#   md5 check __main__.py

# remotive topology generate -f instances/main.instance.yaml -f settings/... --name passenger_welcome build/

# assert interfaces.json namespaces:
#   DoorECU → DoorECU-BodyCan0
#   SeatECU → SeatECU-BodyCan0
#   LightControlECU → LightControlECU-BodyCan0
#   CentralHPC → CentralHPC-BodyCan0
```

Commands: `up|ui`, `down`, `test`, `test-only`, `help` (test body can stub until Task 4).

- [ ] **Step 2: Run generate path**

```bash
bash test_env/remotivelabs-topology-examples/passenger_welcome/scripts/run_passenger_welcome_ui.sh help
# then run topology-only portion, or:
bash .../run_passenger_welcome_ui.sh down  # no-op ok
# Invoke generate by running test-only with skip tests temporarily, OR extract do_generate function and call it
```

Minimum: manually run the generate+topology section once and confirm:

```bash
test -f models/door_ecu/__main__.py
test -f models/seat_ecu/__main__.py
test -f models/light_control_ecu/__main__.py
test -f models/central_hpc/__main__.py
grep 'CanNamespace("SeatECU-BodyCan0"' models/seat_ecu/__main__.py
grep 'WelcomeStatus.WelcomeComplete' models/central_hpc/__main__.py
test -f build/passenger_welcome/docker-compose.yml
grep 'DoorECU-BodyCan0' build/passenger_welcome/ecus/DoorECU/configuration/interfaces.json
grep 'CentralHPC-BodyCan0' build/passenger_welcome/ecus/CentralHPC/configuration/interfaces.json
```

Expected: all present; zero-patch namespaces.

- [ ] **Step 3: Commit nested / note local**

```bash
git add passenger_welcome/scripts passenger_welcome/models  # if models should not commit generated, commit script only and regenerate in CI
```

Prefer **commit script + instances + DBC; regenerate models in script always** (models may be gitignored or committed for offline). Match door pattern: door committed models after pure-copy — commit pure-copied models for convenience.

---

### Task 4: Golden-path E2E test + wire script test commands

**Files:**
- Create: `passenger_welcome/tests/conftest.py`
- Create: `passenger_welcome/tests/test_passenger_welcome_e2e.py`
- Modify: `passenger_welcome/scripts/run_passenger_welcome_ui.sh` (`test` / `test-only`)

**Interfaces:**
- Consumes: live stack; `BrokerClient`, `RestbusSignalConfig`, `capture_frames`, `PingRequest`, `ControlClient`
- Produces: `test_welcome_golden_path` green

- [ ] **Step 1: conftest**

```python
from __future__ import annotations
import os
import pytest

def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--broker_url",
        action="store",
        default=os.environ.get("BROKER_URL", "http://127.0.0.1:50051"),
        type=str,
        help="Broker URL",
    )
```

- [ ] **Step 2: Write E2E test**

`tests/test_passenger_welcome_e2e.py`:

```python
"""Passenger Welcome golden path: Door open → Central fan-out → WelcomeComplete."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio
from remotivelabs.broker import BrokerClient, RestbusSignalConfig
from remotivelabs.topology.behavioral_model import PingRequest
from remotivelabs.topology.control import ControlClient
from remotivelabs.topology.testing.frames import capture_frames

_MODELS = Path(__file__).resolve().parents[1] / "models"
_NS = "DOOR_CTRL-BodyCan0"  # observer + door commander on shared BodyCan0

_DOOR_CMD = "DoorCmd.TargetPosition"
_DOOR_STATUS = "DoorStatus"
_POS = "DoorStatus.CurrentPosition"
_DOOR_DONE = "DoorStatus.IsDone"
_SEAT_STATUS = "PW_SeatStatus"
_SEAT_POS = "PW_SeatStatus.SeatPosition"
_SEAT_DONE = "PW_SeatStatus.IsDone"
_LIGHT_FRAME = "PW_AmbientLight"
_AMBIENT = "PW_AmbientLight.AmbientLight"
_WELCOME_FRAME = "WelcomeStatus"
_WELCOME = "WelcomeStatus.WelcomeComplete"

_WELCOME_SEAT = 5.0
_WELCOME_AMBIENT = 1.0
_OPEN_TARGET = 100.0


class TestStaticPureCopy:
    def test_four_models_exist(self):
        for pkg in ("door_ecu", "seat_ecu", "light_control_ecu", "central_hpc"):
            assert (_MODELS / pkg / "__main__.py").is_file()

    def test_namespaces_zero_patch(self):
        expect = {
            "door_ecu": "DoorECU-BodyCan0",
            "seat_ecu": "SeatECU-BodyCan0",
            "light_control_ecu": "LightControlECU-BodyCan0",
            "central_hpc": "CentralHPC-BodyCan0",
        }
        for pkg, ns in expect.items():
            src = (_MODELS / pkg / "__main__.py").read_text()
            assert f'"{ns}"' in src
            assert f'["[{ns}]' not in src  # no raw bus in live keys


@pytest_asyncio.fixture()
async def broker_client(request: pytest.FixtureRequest) -> AsyncIterator[BrokerClient]:
    url = request.config.getoption("broker_url")
    async with BrokerClient(url=url) as broker, ControlClient(broker) as cc:
        for ecu in ("DOOR_CTRL", "DoorECU", "SeatECU", "LightControlECU", "CentralHPC"):
            await cc.send(target_ecu=ecu, request=PingRequest(), timeout=1, retries=15)
        yield broker


async def _set_door_target(broker: BrokerClient, value: float) -> None:
    await broker.restbus.update_signals(
        (_NS, [RestbusSignalConfig.set(name=_DOOR_CMD, value=value)])
    )


async def _wait_sig(
    broker: BrokerClient,
    frame: str,
    match: dict[str, float],
    *,
    timeout: float,
) -> None:
    async with capture_frames((broker, _NS), [frame]) as cap:
        await cap.wait_for_frame(frame, match, timeout=timeout)


@pytest.mark.asyncio
@pytest.mark.timeout(40, func_only=True)
async def test_welcome_golden_path(broker_client: BrokerClient):
    # Let Central observe boot Door IsDone (pos 0 → done) and latch prev_door_done.
    await asyncio.sleep(1.0)
    await _set_door_target(broker_client, 0.0)
    await _wait_sig(
        broker_client, _DOOR_STATUS, {_DOOR_DONE: 1.0, _POS: 0.0}, timeout=8.0
    )
    await asyncio.sleep(0.5)
    # Move 0→100: IsDone goes 0 while moving then 1 → Central false→true edge.
    await _set_door_target(broker_client, _OPEN_TARGET)

    await _wait_sig(
        broker_client,
        _DOOR_STATUS,
        {_POS: _OPEN_TARGET, _DOOR_DONE: 1.0},
        timeout=8.0,
    )
    await _wait_sig(
        broker_client,
        _SEAT_STATUS,
        {_SEAT_POS: _WELCOME_SEAT, _SEAT_DONE: 1.0},
        timeout=10.0,
    )
    await _wait_sig(
        broker_client,
        _LIGHT_FRAME,
        {_AMBIENT: _WELCOME_AMBIENT},
        timeout=5.0,
    )
    await _wait_sig(
        broker_client,
        _WELCOME_FRAME,
        {_WELCOME: 1.0},
        timeout=8.0,
    )
```

Adjust match dtypes if broker returns int (use `1` vs `1.0` as door suite does). Prefer copy door suite’s float style that already works.

**Door edge strategy (required):** settle at 0 with IsDone=1 so Central latches `prev_door_done=true`, then command 100 so IsDone drops then rises — Central `start_welcome_on_door_edge` needs false→true. If IsDone never drops while moving (bug), fail loud.

If golden path flakes because IsDone stays 1 during step (should be 0 while moving): that is Door YAML behavior (`IsDone = arrived`); during move IsDone=0 — good.

- [ ] **Step 3: Wire script test / test-only**

Same as door script:

- `test-only`: profiles ui+tester (or tester), up -d, sleep, pytest `test_passenger_welcome_e2e.py`, down
- `test`: pytest against running stack
- broker URL `http://topology-broker.com:50051` inside compose network

- [ ] **Step 4: Run E2E**

```bash
bash test_env/remotivelabs-topology-examples/passenger_welcome/scripts/run_passenger_welcome_ui.sh test-only all
```

Expected: static tests + `test_welcome_golden_path` PASSED.

If fail: read door/central logs via `docker compose logs`; fix **YAML or DBC or test waits only** — not hand model.

- [ ] **Step 5: Commit**

```bash
# monorepo if any doc touch; nested for passenger_welcome tests/script
git commit -m "test(pw): passenger welcome golden-path E2E"
```

---

### Task 5: Verification + teaching checklist closeout

**Files:**
- Modify (optional): `workspace/passenger_welcome_eca/README.md` — one section “Live E2E” pointing to `passenger_welcome` + script
- No compiler change expected

- [ ] **Step 1: Full verify commands**

```bash
export PYTHONPATH=".../bmgen_ECA/src:${PYTHONPATH:-}"
# unit compiler still green
cd bmgen_ECA && python3 -m pytest tests/ -q
# parse examples
# test-only all
bash .../passenger_welcome/scripts/run_passenger_welcome_ui.sh test-only all
# getting_started door still works (optional sanity)
bash .../getting_started/scripts/run_bmgen_door_ecu_ui.sh test-only all
```

Expected: bmgen_ECA tests pass; PW golden path pass; door suite still pass if run.

- [ ] **Step 2: Teaching checklist (human)**

Confirm human can explain design §9 items (shared channel, bus=NS, pure-copy, WelcomeComplete, edge).

- [ ] **Step 3: Final commit if README updated**

```bash
git add workspace/passenger_welcome_eca/README.md
git commit -m "docs(pw): link passenger_welcome Remotive E2E"
```

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| Align 4 YAML buses | T1 |
| WelcomeComplete TX | T1 |
| New topology not getting_started | T2 |
| DBC frames + senders | T2 |
| Pure generate ×4 | T3 |
| Zero-patch namespace assert | T3 |
| Golden path pytest | T4 |
| Run script pipeline | T3–T4 |
| Door IsDone edge handling | T4 test strategy |
| No multi-bus compiler | Global + no task |
| getting_started untouched | Global |

Placeholder scan: none intentional. Package names match `snake_case`. DBC IDs 200/201/300/301/400/401/500 unique.
