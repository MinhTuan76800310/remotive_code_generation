# Topology facts (Passenger Welcome / shared BodyCan0)

Evidence: `interfaces.json` + `body_can.dbc` under the topology build.

| Fact | Detail |
|------|--------|
| Physical channel | One `BodyCan0` (UDP multicast). Peer TX is visible on every ECU's own NS. |
| Namespace shape | `{ecu}-{channel}` e.g. `DoorECU-BodyCan0` — equals schema bus string (zero-patch). |
| Observer / mock NS | `DOOR_CTRL-BodyCan0` — tests publish DoorCmd and subscribe status frames here. |
| Door command owner | DBC: `DoorCmd` sender = **DOOR_CTRL** → inject on `DOOR_CTRL-BodyCan0`. |
| Seat command owner | DBC: `PW_SeatCmd` sender = **CentralHPC** → inject on `CentralHPC-BodyCan0`. |
| Light command owner | DBC: `PW_AmbientLightCmd` sender = **CentralHPC** → inject on `CentralHPC-BodyCan0`. |
| Live signal keys | `Frame.Signal` only (bus stripped). IR still stores `[Bus]Frame.Signal`. |
| Boot welcome | Door init `IsDone=true` at pos 0 → Central false→true edge memory may fire → sticky SeatCmd=5 / AmbientReq=1 after models start. |
| Pure copy | `models/{pkg}/__main__.py` byte-identical to `bmgen-eca generate` output (md5). |

## Remotive restbus note

`restbus.update_signals` only sticks if a **cyclic restbus owner** already transmits that frame.
After first welcome, **Central's model** owns SeatCmd/AmbientCmd cycles — mock inject on DOOR_CTRL loses the bus fight.
