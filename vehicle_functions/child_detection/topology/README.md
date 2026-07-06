# Child detection — Remotive topology E2E (generated code)

End-to-end tests for Python under `../generated/`, following
[`getting_started`](../../test_env/remotivelabs-topology-examples/getting_started/tests/test_hazard_light.py):

- `pytest` + `BrokerClient.restbus.update_signals` (stimulus)
- `capture_frames` + `wait_for_frame` (oracle)
- `ControlClient` + `PingRequest` per ECU (readiness)

## Layout

```
topology/
├── instances/main.instance.yaml
├── platform/databases/cpd.dbc
├── models/*/python/          # sync from ../generated/
├── tests/
│   ├── test_child_detection_generated.py
│   ├── conftest.py
│   ├── pyproject.toml
│   └── tester.instance.yaml
├── Dockerfile
└── run-e2e.sh
```

## Workflow

```bash
# 1) Regenerate models from inc_schema (from repo root)
cd remotive-bm-compiler
uv run bmgen generate ../vehicle_functions/child_detection/inc_schema/centralHPC.yaml --out ../vehicle_functions/child_detection/generated/central_hpc
# ... other ECUs, or your existing generate script

# 2) Copy into topology + patch CAD_logic
cd ../vehicle_functions/child_detection
./sync-generated-to-topology.sh

# 3) E2E
cd topology
./run-e2e.sh
```

Manual generate + test:

```bash
cd vehicle_functions/child_detection/topology
remotive topology generate \
  -f instances/main.instance.yaml \
  -f settings/can_over_udp.settings.instance.yaml \
  --name child_detection_generated \
  build

docker compose -f build/child_detection_generated/docker-compose.yml \
  --profile tester up --build --abort-on-container-exit tester
```

## CAD truth table under test (`inc_schema/SWC_CAD_logic.yaml`)

| seat | camera | airbag report | sum | alert |
|------|--------|---------------|-----|-------|
| 1 | 1 | 1 | 4 | ON |
| 0 | 1 | 1 | 3 | ON (boundary) |
| 1 | 1 | 0 | 2 | OFF |

`centralhpc` uses `REMOTIVE_BROKER_URL=http://topology-broker.com:50051` for multi-namespace fan-in.