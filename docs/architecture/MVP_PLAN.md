# MVP Plan — Remotive Behavioral Model Compiler

## Problem Statement

Creating Remotive Behavioral Model Python code is currently a manual, error-prone process. Engineers must:
- Understand the Remotive `BehavioralModel` Python API (namespace types, `FrameFilter`, `restbus.update_signals`, state machines, periodic tickers)
- Hand-write async handler methods with correct signatures (`async def on_x(self, frame: Frame) -> None`)
- Manually configure namespace wiring (`CanNamespace`, `RestbusConfig`, `SenderFilter`)
- Manually implement state machines, toggle logic, and blinking patterns
- Manually ensure lifecycle correctness (startup, shutdown, reset/reboot)

This leads to:
- **Copy-paste boilerplate**: Every model follows the same structural pattern but is written manually
- **Silent bugs**: Incorrect namespace references, missing `RestbusConfig`, wrong signal names
- **No systematic verification**: No automated way to verify that generated code is structurally sound, behaviorally correct, or compositionally consistent
- **Slow iteration**: Changing a signal mapping or adding a handler requires editing multiple interconnected code sections

## Goals

1. **Deterministic code generation**: A small YAML spec → typed IR → deterministic compiler → correct Remotive Behavioral Model Python code
2. **3-layer verification**: Every generated model passes structural, behavioral, and composition verification before entering CI
3. **Recipe-based pattern reuse**: Known ECU behavior patterns (DirectSignalMapping, ToggleButtonState, PeriodicBlinkingOutput) are codified as recipes, not reinvented each time
4. **End-to-end MVP**: The system works from YAML to verified Python code in a single `bmgen generate → bmgen verify` pipeline
5. **CI-ready**: Generated code that fails verification is rejected; CI only accepts verified artifacts

## Non-Goals

1. **Generating topology YAML** — this project generates behavioral model *Python code*, not Remotive topology configuration
2. **GraphRAG / Neo4j / knowledge graph** — the MVP uses a flat recipe registry, not a graph database
3. **Agent-generated code** — the MVP compiler is deterministic; no LLM writes final Python code in the MVP pipeline
4. **MCP plugin integration** — no Claude Code MCP server in MVP
5. **SOME/IP bridge** — SOME/IP namespace support is future work (the GWM/IHU examples show this pattern but it's not in MVP scope)
6. **Cuttlefish/Android integration** — the IHU model bridges to Android emulator/Cuttlefish; this is outside MVP scope
7. **Multi-ECU orchestration** — the MVP handles one ECU per spec; orchestrating multiple ECUs is future work
8. **LIN namespace support** — the RL/RLCM examples show LIN patterns; this is future work for MVP+
9. **State machine library integration** — the `transitions` library pattern (used in the full BCM model) is complex; MVP handles simpler toggle/blink patterns first

## MVP Scope

### What's In

| Component | Description |
|-----------|-------------|
| YAML Spec Parser | Parses a small YAML file describing ECU behavior into raw spec dict |
| Typed IR Builder | Converts raw spec into validated `BehavioralModelIR` with invariant checks |
| Recipe Registry | Flat registry of known behavior patterns (DirectSignalMapping, ToggleButtonState) |
| Deterministic Compiler | Generates complete Remotive Behavioral Model Python code from IR + recipes |
| Jinja2 Templates | Template-based code generation (no LLM in the MVP path) |
| 3-Layer Verifier | Structural (T1), Behavioral (T2), Composition (T3) checks on generated code |
| CLI (`bmgen`) | `bmgen generate` and `bmgen verify` commands |
| CI Workflow | GitHub Actions workflow that runs `bmgen verify` on generated code |

### MVP Patterns

| Pattern | Description | Priority |
|---------|-------------|----------|
| `DirectSignalMapping` | Read one input signal → write same value to one or more output signals via `restbus.update_signals` | P0 |
| `ToggleButtonState` | Read button signal → toggle internal boolean → write state to output signals | P0 |
| `PeriodicBlinkingOutput` | Internal state enables/disables blinking → periodic async task → cleanup/reset | P1 (MVP+) |

### What's Out (Future Scope)

| Feature | Priority | Notes |
|---------|----------|-------|
| SOME/IP namespace handlers | P2 | Pattern exists in GWM/IHU examples |
| LIN namespace support | P2 | Pattern exists in RL/RLCM examples |
| `transitions` state machine library | P2 | Full BCM model uses this for complex state |
| Agent-assisted novel logic | P2 | For `novel_logic` escape hatch |
| GraphRAG knowledge base | P3 | Recipe evolution and cross-model pattern mining |
| MCP plugin for Claude Code | P3 | Interactive model generation in IDE |
| Multi-ECU orchestration spec | P3 | Multiple ECUs in one topology |
| Cuttlefish/Android bridge | P3 | IHU-style device bridging |

## Milestones

### M1: Foundation (Week 1-2)
- Repository structure created
- IR dataclasses defined with all required fields
- YAML input schema defined and parser implemented
- IR validation (all invariants) implemented
- Example YAML specs written (`bcm_direct.yaml`, `bcm_toggle.yaml`)

**Acceptance**: `bmgen parse examples/bcm_direct.yaml` produces valid `BehavioralModelIR` with no invariant violations

### M2: DirectSignalMapping Recipe + Compiler (Week 2-3)
- Recipe registry implemented with `DirectSignalMapping` recipe
- Jinja2 template `main.py.j2` created
- Compiler generates complete Python behavioral model code
- Generated code is syntactically valid Python

**Acceptance**: `bmgen generate examples/bcm_direct.yaml --out generated/` produces a Python file that imports successfully and matches the getting_started BCM pattern

### M3: ToggleButtonState Recipe (Week 3-4)
- `ToggleButtonState` recipe added to registry
- Template handles state variables, toggle logic, reset handler
- Generated toggle handler passes behavioral verification

**Acceptance**: `bmgen generate examples/bcm_toggle.yaml --out generated/` produces code where pressing once → enabled, pressing twice → disabled

### M4: T1 Structural Verifier (Week 4-5)
- Structural verifier checks: file exists, syntax valid, imports succeed, handler async, handler accepts frame, namespace references valid, output namespace has restbus, input handler has FrameFilter
- Verification report JSON output implemented

**Acceptance**: `bmgen verify generated/` produces a JSON report with all T1 checks passing for DirectSignalMapping and ToggleButtonState models

### M5: T2 Behavioral Verifier (Week 5-6)
- Behavioral verifier: fake Frame → call handler → check mocked restbus.update_signals output
- DirectSignalMapping behavioral test
- ToggleButtonState behavioral test (press once/twice)

**Acceptance**: Behavioral verifier confirms DirectSignalMapping forwards signals correctly and ToggleButtonState toggles on/off correctly

### M6: T3 Composition Verifier + CI (Week 6-7)
- Composition verifier: duplicate handler names, duplicate state ownership, pattern conflicts, periodic cleanup, reset coverage, lifecycle checks
- GitHub Actions workflow for `bmgen verify`
- PeriodicBlinkingOutput recipe (P1)

**Acceptance**: CI pipeline rejects code that fails any T1/T2/T3 check; PeriodicBlinkingOutput generates with cleanup and reset

## Acceptance Criteria (Overall MVP)

1. **End-to-end**: A user can write a YAML spec, run `bmgen generate`, run `bmgen verify`, and get PASS for DirectSignalMapping and ToggleButtonState
2. **Deterministic**: The same YAML spec always produces the same Python code (no randomness, no LLM)
3. **No raw LLM code**: Every line of generated Python comes from templates + recipe logic, not from an Agent or LLM
4. **Valid Remotive API**: Generated code uses correct `remotivelabs.topology` imports, `CanNamespace`, `RestbusConfig`, `FrameFilter`, `restbus.update_signals` patterns as seen in the reference examples
5. **Verifiable**: T1, T2, T3 checks all produce JSON reports with PASS/FAIL status
6. **CI-ready**: A GitHub Actions workflow runs `bmgen verify` and gates on PASS status
7. **Novel logic escape hatch**: If a YAML spec contains behavior that no recipe can handle, the system marks it as `novel_logic` and fails early rather than generating incorrect code
