# Isolation strategy

## Drive path per component

| Component | Drive | Observe | Why |
|-----------|-------|---------|-----|
| DoorECU | `DOOR_CTRL-BodyCan0:DoorCmd.TargetPosition` | DoorStatus.* on DOOR_CTRL | DBC sender = DOOR_CTRL |
| SeatECU | **Hijack** `CentralHPC-BodyCan0:PW_SeatCmd.SeatPosTarget` | PW_SeatStatus.* on DOOR_CTRL | Central owns cyclic SeatCmd after welcome |
| LightControlECU | **Hijack** `CentralHPC-BodyCan0:PW_AmbientLightCmd.AmbientReq` | PW_AmbientLight.* on DOOR_CTRL | same as seat |
| CentralHPC | Door open only (false→true IsDone edge) | seat + light + WelcomeComplete | no direct state API |

## Hijack pattern (Python)

```python
OWN = "CentralHPC-BodyCan0"
OBS = "DOOR_CTRL-BodyCan0"

async def set_seat(broker, value: float) -> None:
    await broker.restbus.update_signals(
        (OWN, [RestbusSignalConfig.set(name="PW_SeatCmd.SeatPosTarget", value=float(value))])
    )

async def set_door(broker, value: float) -> None:
    await broker.restbus.update_signals(
        (OBS, [RestbusSignalConfig.set(name="DoorCmd.TargetPosition", value=float(value))])
    )
```

## Never do

```bash
# Wipes model TX config → golden path dead until force-recreate
remotive broker restbus reset --namespace CentralHPC-BodyCan0
remotive broker restbus reset --namespace SeatECU-BodyCan0
```

Safe: reset/add only on mock `DOOR_CTRL-BodyCan0` (DoorCmd).

## Recover broken stack

```bash
docker compose -f build/.../docker-compose.yml --profile ui up -d --force-recreate \
  door_ecu seat_ecu light_control_ecu central_hpc door_ctrl-mock \
  DoorECU-broker.com SeatECU-broker.com LightControlECU-broker.com \
  CentralHPC-broker.com DOOR_CTRL-broker.com
```

Do **not** stop Central mid-suite as isolation — use hijack instead.
