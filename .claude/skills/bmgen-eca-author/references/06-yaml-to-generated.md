# YAML → generated Behavioral Model

Phase 1 skill stops at parse green. Read this when the user asks what runtime looks like or requests generate.

## Output layout

```text
{--out}/bmgen_generated/<snake_case(ecu_mock.name)>/
  __init__.py
  __main__.py
```

Example: `DoorECU` → `bmgen_generated/door_ecu/`.

## Mapping table

| YAML | Generated |
|------|-----------|
| `ecu_mock.name` | class name + package dir + `SenderFilter(ecu_name=…)` |
| unique signal bus | `CanNamespace("<bus>", …)` |
| RX/TX on same `(bus, frame)` | **one** `async def on_<Frame>(self, frame)` |
| `on_rx` rules same frame | sequential in handler, YAML order |
| `on_timer` rules same timer | one `while True: sleep(interval)` loop, YAML order |
| `parameters` | class attributes with `value` defaults |
| `state` + `init` | class attributes with `init` defaults |
| `timers` + `auto_start` | ticker tasks started when BM starts |
| `condition: "true"` | actions without `if` (always) |
| other condition | `if <lowered_python>:` |
| `set_state` | `self.<name> = <payload_py>` |
| `tx` | namespace signal write of lowered payload |
| `min`/`max`/`abs` | `np.minimum.reduce` / `np.maximum.reduce` / `np.abs` |

## Annotated DoorECU slice

YAML rule `receive_target` (on_rx DoorCmd.TargetPosition) becomes part of the **DoorCmd** frame handler: read `TargetPosition` from `frame.signals`, assign clamped value to `self.target_pos`.

YAML rules `move_door` + `publish_status` (both on_timer `tick`) share one ticker loop: first step position, then update `door_moving` and TX status — because that is YAML order.

## Generate command

```bash
bmgen-eca generate path/to/ecu.yaml --out .
# → ./bmgen_generated/<ecu_snake>/
bmgen-eca verify ./bmgen_generated/<ecu_snake>
```

Only run generate if the user asks. Parse green is enough for authoring DONE.
