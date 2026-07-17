# Suite layout (door-style)

## Files

```text
tests/
  conftest.py                 # --broker_url
  _bus.py                     # OBS/OWN, set_door/set_seat/set_light, wait_frame, settle
  test_door_component.py
  test_seat_component.py
  test_light_component.py
  test_central_component.py
  test_passenger_welcome_bmgen.py   # integration / golden path
```

## Per-file structure

1. **Module docstring** — drive NS, observe NS, run command.
2. **`TestXxxStatic`**
   - model file exists under `models/<pkg>/__main__.py`
   - `Frame.Signal` keys present; raw `[Bus]…` **not** in signal dict keys
   - `CanNamespace("…-BodyCan0")` + `ecu_name="…"`
   - component-specific: params, WelcomeComplete clear+set, etc.
3. **Runtime cases** (`@pytest.mark.asyncio` + timeout)
   - settle / drive / wait
   - edges: clamp, mid target, retarget, IsMoving, return-to-0, second cycle

## Timeouts from YAML

| ECU | Formula |
|-----|---------|
| Door | `steps * tick + margin` (step 10 / 0.2s → full 0→100 ≈ 2s + 3s margin) |
| Seat | `startup_ticks * 0.1 + |delta| * 0.1 + margin` (20×0.1 = 2s startup) |
| Light | 5s (event TX, no motion) |
| Central join | door timeout + seat timeout + light + WelcomeComplete margin |

## Wait discipline

- Prefer **pos first**, then **IsDone** (same-tick combined match can flake).
- Combined match OK after motion has settled.
- Same-value light skip: hard to assert on sticky restbus — assert **distinct** levels only.

## Run script aliases

```bash
test door|seat|light|central   # one suite file
test components                # four component files
test integ                     # golden integration only
test all                       # integ + components
```

Map aliases → pytest file paths; keep numeric node-ids for integration cases.
