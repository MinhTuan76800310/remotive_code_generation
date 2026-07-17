# bmgen-eca

**ECA `schema_v2` → Remotive Behavioral Model compiler.**

Standalone product. It does **not** use recipe-based `remotive-bm-compiler` / `bmgen.*` plugins (no ActuatorCommand, WeightedLogOdds, etc.). Input is pure **schema_v2** ECU YAML; output is a drop-in Remotive `BehavioralModel` package.

| | |
|--|--|
| Package | `bmgen-eca` (`pip` / `bmgen-eca` CLI) |
| Python | ≥ 3.11 |
| Dialect | `apiVersion` + `ecu_mock.name` + `behavior` |
| Live keys | Remotive `Frame.Signal` (bus stripped); `CanNamespace` = YAML bus string |
| Design log | [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md) |

---

## Install

```bash
git clone https://github.com/MinhTuan76800310/bmgen_ECA.git
cd bmgen_ECA
pip install -e ".[dev]"
```

Compiler deps: `PyYAML`, `Jinja2`.  
**Generated** models also need **runtime** `numpy` + Remotive SDK (`remotivelabs-*`) inside the topology image — not required just to parse/generate.

---

## CLI

```bash
# frozen diagnostic catalog (public contract)
bmgen-eca errors

# parse + semantic; print IR summary / diagnostics
bmgen-eca parse path/to/ecu.yaml

# emit Remotive BM package
bmgen-eca generate path/to/ecu.yaml --out /tmp/out
# → /tmp/out/bmgen_generated/<ecu_package>/{__init__.py,__main__.py}

# syntax / structural verify of generated package
bmgen-eca verify /tmp/out/bmgen_generated/<ecu_package>
```

`parse` is the hard gate for authoring: exit 0 with **zero** `E_*` diagnostics before you claim YAML is done.

---

## Dialect (schema_v2)

- **Root:** `apiVersion`, `ecu_mock.name`, `behavior`
- **Signals:** `[Bus]Frame.Signal`  
  - `Bus` → Remotive `CanNamespace("Bus")` (use `{Ecu}-{Channel}` for zero-patch live, e.g. `DoorECU-BodyCan0`)  
  - Live frame/signal keys → `Frame.Signal` only
- **Expr:** `$state.x`, `$para.x`, `$[Bus]Frame.Signal`, `min` / `max` / `abs`, numeric ops  
  - No bare `$name`, no arbitrary Python
- **Rules:** `on_rx` / `on_timer` triggers; actions `set_state` | `tx`
- **Errors:** `bmgen-eca errors` — codes like `E_BARE_IDENT`, `E_UNRESOLVED_IDENT`, `E_TRIGGER_TARGET`

Minimal shape:

```yaml
apiVersion: v1.0
ecu_mock:
  name: DoorECU
behavior:
  interfaces:
    can_rx:
      - signal: "[DoorECU-BodyCan0]DoorCmd.TargetPosition"
    can_tx:
      - signal: "[DoorECU-BodyCan0]DoorStatus.CurrentPosition"
    someip_tx: []
  parameters: []
  state: []
  timers: []
  rules: []
```

See fixture: [`tests/fixtures/schema_v2.yaml`](tests/fixtures/schema_v2.yaml).

---

## Live Remotive (pure copy)

Proven path for multi-ECU scenarios (e.g. Passenger Welcome):

1. `bmgen-eca generate <yaml> --out …` per ECU  
2. **Pure-copy** `bmgen_generated/<pkg>/` → topology `models/<pkg>/` (md5 check; **no hand edit**)  
3. `remotive topology generate` + compose up  
4. Pytest against live broker — containers stay up; tests only change signals  

Namespace rule: YAML bus **is** Remotive `{ecu}-{channel}` → **zero-patch** `interfaces.json`.

TX values go through `_net()` so numpy scalars are not sent to restbus.

---

## Claude Code skills

This repo ships **project-local** Claude skills under [`.claude/skills/`](.claude/skills/). They load when you open this project in Claude Code (no marketplace install).

### 1. `bmgen-eca-author` — NL → schema_v2 YAML

Path: [`.claude/skills/bmgen-eca-author/`](.claude/skills/bmgen-eca-author/)

| | |
|--|--|
| **When** | Write / fix ECU mock YAML, ECA behavior, door/seat/light schema_v2, or repair `E_*` parse errors |
| **Command** | `/bmgen-eca-yaml` (see [`.claude/commands/bmgen-eca-yaml.md`](.claude/commands/bmgen-eca-yaml.md)) |
| **Truth** | `bmgen-eca parse <file>` — zero `E_*` before DONE |
| **Hard rules** | Prefixed `$state` / `$para` / `$[Bus]…` only; `min`/`max`/`abs` only; one bus per ECU (MVP); exact signal strings |

**Workflow:** read field-graph + structure refs → write providers first → rules → `parse` loop until green → generate only if asked.

**Hook:** [`.claude/hooks/bmgen-eca-parse-gate.sh`](.claude/hooks/bmgen-eca-parse-gate.sh) runs on Write/Edit of ECA YAML (PostToolUse) so a bad file cannot “finish” silently. Config: [`.claude/settings.json`](.claude/settings.json).

Atlas: `references/00–07` + `examples/door_ecu.min.yaml` inside the skill.

### 2. `bmgen-eca-live-test` — multi-ECU live component tests

Path: [`.claude/skills/bmgen-eca-live-test/`](.claude/skills/bmgen-eca-live-test/)

| | |
|--|--|
| **When** | Per-ECU edge cases, keep-stack-up pytest, restbus inject isolation, flaky WelcomeComplete / SeatCmd |
| **Contract** | `up` once → `test door\|seat\|light\|central\|…` many times → **no auto-down** |
| **Inject rule** | Drive on **DBC / runtime restbus owner** NS; observe on mock NS |
| **Seat / Light** | Hijack **CentralHPC** restbus for `SeatCmd` / `AmbientReq` (not DOOR_CTRL) after welcome |
| **Never** | `restbus reset` on model namespaces (`*ECU-*`, `CentralHPC-*`) — kills golden path |

**Workflow:** confirm stack up → identify DBC senders → helpers in `tests/_bus.py` → static pure-copy asserts → runtime edges → suite aliases on run script → report pass counts with containers still Up.

Refs: topology facts, isolation strategy, suite layout, failure matrix, run contract (`references/00–04`).

---

## Design

Architecture, live-key choices, and acceptance rows: **[DESIGN_DECISIONS.md](DESIGN_DECISIONS.md)**.

Pipeline (high level): **Parse → Symbols → Resolve → Semantic → IR → Jinja codegen → Verify**.

---

## Tests

```bash
python -m pytest tests/ -v
```

Unit/acceptance matrix covers parse green/red, codegen keys/namespace, and CLI. Live multi-ECU E2E lives in the consumer topology (not this package’s pytest).

---

## License / product boundary

- **This repo:** compiler + Claude authoring/test skills + design log.  
- **Not in this repo:** full Remotive topology trees, DBC, docker compose (consumer projects own those; skills describe how to test against them).
