# Acceptance checklist — bmgen-eca-live-test

## Scripted

- [x] Skill file exists; description mentions live Remotive / component / keep-stack-up
- [x] references/00–04 present (topology, isolation, suite layout, failures, run)
- [x] Hard rules forbid model-NS restbus reset
- [x] Hijack Central for SeatCmd/AmbientCmd documented
- [x] Run contract: `up` once, `test <suite>` many times, no auto-down
- [x] DONE requires green suite + containers still Up

## Live proof (host stack)

- [x] `test door` 10/10 (2026-07-17)
- [x] `test seat` 8/8
- [x] `test light` 7/7
- [x] `test central` 8/8
- [x] `test integ` 9/9
- [x] containers still Up after all suites

## Manual

- [ ] Skill engages on "viết test case cho từng component passenger welcome"
- [ ] Agent does not restbus-reset CentralHPC when debugging seat
