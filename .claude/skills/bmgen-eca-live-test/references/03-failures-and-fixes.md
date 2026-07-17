# Failures → fixes (live)

| # | Symptom | Root cause | Fix |
|---|---------|------------|-----|
| 1 | Seat inject via DOOR_CTRL never moves | Central restbus keeps SeatCmd=5 after welcome | Hijack **CentralHPC** `PW_SeatCmd.SeatPosTarget` |
| 2 | Light inject flaky / stuck | Competing DOOR_CTRL AmbientCmd restbus | Do **not** add AmbientCmd on DOOR_CTRL; only Central |
| 3 | After `restbus reset CentralHPC` golden dies | Model restbus config wiped | Never reset model NS; force-recreate containers |
| 4 | Pos reached but IsDone match times out | Same-tick / capture window | Wait pos first, then IsDone |
| 5 | Fresh stack: SeatCmd not on bus | No cyclic restbus yet | Boot welcome creates Central TX; or wait for models + first door edge |
| 6 | `update_signals` alone no effect | No restbus owner for frame | Inject on owner NS that already cycles the frame |
| 7 | WelcomeComplete sticky on re-test | Level 1 never re-edges | Central YAML TX WelcomeComplete=0 on start rule |
| 8 | Seat stuck mid-step after probes | Corrupted restbus / dual injectors | Force-recreate ECU+broker containers; re-run golden |
| 9 | Bus shows SeatCmd=5 while you set 6 | Central still winning the cycle | Confirm update on **OWN** NS; remove DOOR_CTRL SeatCmd restbus |

## Debug probes (safe)

```bash
# Observe only — do not reset model NS
remotive broker restbus update --url http://localhost:50051 \
  --signal CentralHPC-BodyCan0:PW_SeatCmd.SeatPosTarget:8

# Capture via tester container / python capture_frames on DOOR_CTRL-BodyCan0
```

## Anti-patterns

- Stopping Central "to free the bus" for seat tests (breaks keep-stack-up contract).
- Adding SeatCmd restbus on both DOOR_CTRL and Central (bus fight).
- Assuming shared channel means shared **restbus ownership**.
