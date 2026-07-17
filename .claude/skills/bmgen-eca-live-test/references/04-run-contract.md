# Run contract

## Keep stack up

```bash
# once
bash test_env/remotivelabs-topology-examples/passenger_welcome/scripts/run_passenger_welcome_ui.sh up

# many times — pytest only, no generate, no down
bash .../run_passenger_welcome_ui.sh test door
bash .../run_passenger_welcome_ui.sh test seat
bash .../run_passenger_welcome_ui.sh test light
bash .../run_passenger_welcome_ui.sh test central
bash .../run_passenger_welcome_ui.sh test components
bash .../run_passenger_welcome_ui.sh test integ
bash .../run_passenger_welcome_ui.sh test all

# explicit teardown only when user wants it
bash .../run_passenger_welcome_ui.sh down
```

## CI one-shot

```bash
bash .../run_passenger_welcome_ui.sh test-only all   # generate + up + pytest + down
```

## Broker URL inside tester

```
http://topology-broker.com:50051
```

Host UI / API: `http://localhost:8080`, `http://localhost:50051`.

## Proven baseline (2026-07-17)

| Suite | Cases |
|-------|------:|
| door | 10 |
| seat | 8 |
| light | 7 |
| central | 8 |
| integ | 9 |
| **Total** | **42** |

All green with ECU containers still Up.
