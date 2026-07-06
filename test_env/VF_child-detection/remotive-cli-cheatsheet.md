# Remotive CLI commands — vf_child_detection

Snippets để inject signal giá trị vào vf_child_detection topology.
URL front-end: `http://localhost:50051` (nginx). Hoặc direct per-ECU broker (xem docker-compose networks).

## Setup URL

```bash
URL=http://localhost:50051   # qua nginx topology-api (recommended)
# SEAT_BROKER=http://10.1.0.6:50051
# DMS_BROKER=http://10.1.0.5:50051
# CENTRAL_BROKER=http://10.1.0.3:50051
# COCKPIT_BROKER=http://10.1.0.4:50051
# AIRBAG_BROKER=http://10.1.0.2:50051
# topology-broker.com:50051 (master)
```

## Discover

```bash
remotive broker signals namespaces --url $URL
remotive broker signals list          --url $URL
remotive broker signals frame-distribution --url $URL --namespace CENTRAL-CpdCan0
```

## Subscribe (xem signal end-to-end)

```bash
remotive broker signals subscribe \
  --url $URL \
  --signal SEAT-CpdCan0:SeatInput.SeatOccupied \
  --signal DMS-CpdCan0:CameraInput.ChildDetectedByCamera \
  --signal DMS-CpdCan0:CameraInput.IsMoving \
  --signal CENTRAL-CpdCan0:ChildAlert.ChildAlertActive \
  --signal COCKPIT-CpdCan0:HmiChildWarning.ChildAlertActive \
  --signal AIRBAG-CpdCan0:AirbagActuatorState.AirbagActuated
```

## One-shot publish (single trigger)

```bash
# Light seat → SeatOccupied=1
remotive broker signals publish \
  --url $URL \
  --signal SEAT-CpdCan0:SeatWeightSensor.WeightKg:4.0

# Adult seat → SeatOccupied=0
remotive broker signals publish \
  --url $URL \
  --signal SEAT-CpdCan0:SeatWeightSensor.WeightKg:75.0

# Camera detect child
remotive broker signals publish \
  --url $URL \
  --signal DMS-CpdCan0:CameraInput.ChildDetectedByCamera:1

# Camera motion (IsMoving)
remotive broker signals publish \
  --url $URL \
  --signal DMS-CpdCan0:CameraInput.IsMoving:1

# Driver turn airbag off
remotive broker signals publish \
  --url $URL \
  --signal COCKPIT-CpdCan0:HmiDriverAction.TurnAirbagOff:1

# Camera via WebSocket (alternative path)
# Run on host: uv run camera_service/camera_ws_server.py --value 1 --moving 1
```

## Continuous injection via restbus

```bash
# A. Register a frame for periodic transmission
remotive broker restbus add \
  --url $URL \
  --frame SEAT-CpdCan0:SeatWeightSensor \
  --start

# B. Update signal value (frame re-emitted at cycle time)
remotive broker restbus update \
  --url $URL \
  --signal SEAT-CpdCan0:SeatWeightSensor.WeightKg:4.0

# C. Stop (pause, keep config)
remotive broker restbus stop \
  --url $URL \
  --namespace SEAT-CpdCan0

# D. Reset (clear all config for namespace)
remotive broker restbus reset \
  --url $URL \
  --namespace SEAT-CpdCan0
```

## E2E truth-table cases (đối chiếu codegen)

| Case | Seat WeightKg | Cam | Mov | Kỳ vọng HmiChildWarning.ChildAlertActive |
|------|---------------|-----|-----|------------------------------------------|
| TC-00 | 75 | 0 | 0 | 0 |
| TC-01 | 4 | 0 | 0 | 0 |
| TC-02 | 75 | 1 | 0 | 0 |
| TC-03 | 75 | 0 | 1 | 0 |
| TC-04 | 4 | 1 | 0 | 1 |
| TC-05 | 4 | 0 | 1 | 0 |
| TC-06 | 75 | 1 | 1 | 1 |
| TC-07 | 4 | 1 | 1 | 1 |

Chi tiết + pytest map: mở `docs/e2e-child-detection-flow.html` hoặc chạy `./run-e2e-tests.sh`.

## End-to-end demo (child alert → driver confirms → airbag actuates)

```bash
# 1. Setup periodic frame injection on each producer ECU
remotive broker restbus add --url $URL --frame SEAT-CpdCan0:SeatWeightSensor --start
remotive broker restbus add --url $URL --frame DMS-CpdCan0:CameraInput --start

# 2. Set inputs that satisfy WeightedLogOdds threshold (sum >= 1.0)
# Weights: Seat=0.3, Camera=0.7, IsMoving=0.3, threshold 1.0
remotive broker restbus update --url $URL \
  --signal SEAT-CpdCan0:SeatWeightSensor.WeightKg:4.0
remotive broker restbus update --url $URL \
  --signal DMS-CpdCan0:CameraInput.ChildDetectedByCamera:1
remotive broker restbus update --url $URL \
  --signal DMS-CpdCan0:CameraInput.IsMoving:1

# 3. Driver decision
remotive broker signals publish --url $URL \
  --signal COCKPIT-CpdCan0:HmiDriverAction.TurnAirbagOff:1

# 4. Subscribe (separate terminal) to see chain
remotive broker signals subscribe --url $URL \
  --signal CENTRAL-CpdCan0:ChildAlert.ChildAlertActive \
  --signal COCKPIT-CpdCan0:HmiChildWarning.ChildAlertActive \
  --signal AIRBAG-CpdCan0:AirbagActuatorState.AirbagActuated
```

## Reset / Cleanup

```bash
# Stop all periodic transmission on each namespace
remotive broker restbus stop  --url $URL --namespace SEAT-CpdCan0
remotive broker restbus stop  --url $URL --namespace DMS-CpdCan0
remotive broker restbus stop  --url $URL --namespace CENTRAL-CpdCan0
remotive broker restbus stop  --url $URL --namespace COCKPIT-CpdCan0
remotive broker restbus stop  --url $URL --namespace AIRBAG-CpdCan0

# Or clear all config
remotive broker restbus reset --url $URL --namespace <NS>
```

## Troubleshooting

```bash
# "Pool overlaps with other one in this address space" — another compose stack uses 10.1.0.0/24
docker network ls | grep -E 'control_network|----control_network'
docker network rm <network_id>

# Check container status
docker compose -f test_env/VF_child-detection/build/vf_child_detection/docker-compose.yml --profile ui ps -a

# View broker logs
docker logs vf_child_detection-CENTRAL-broker.com-1 --tail 30
docker logs vf_child_detection-topology-broker.com-1 --tail 30
```

## Known limitation

`centralhpc` container hiện tại **Exited (1)** vì architectural constraint của Remotive topology mode:
WeightedLogOdds fan-in cần đọc `DMS-CpdCan0` namespace từ CENTRAL's broker (chỉ có `CENTRAL-CpdCan0` namespace).
Workaround options:
- Patch `remotivelabs/topology/behavioral_model` để accept multi-broker
- Tạo custom aggregator broker
- Skip fan-in (để trực tiếp CENTRAL output deterministic)
- Edit `centralhpc/__main__.py` để connect DMS-broker riêng

Đọc thêm: `docs/superpowers/specs/2026-07-03-align-test-env-with-inc-schema.md`.
