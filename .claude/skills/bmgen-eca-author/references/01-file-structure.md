# File structure (root)

## Required shape

```yaml
apiVersion: v1.0
ecu_mock:
  name: DoorECU          # required — class, package dir, SenderFilter
behavior:
  interfaces: { … }
  parameters: [ … ]
  state: [ … ]
  timers: [ … ]
  rules: [ … ]
```

## Field table

| Field | Required | Why |
|-------|----------|-----|
| `apiVersion` | yes | dialect pin (fixture uses `v1.0`) |
| `ecu_mock.name` | yes | only name source; missing → `E_MISSING_ECU_NAME` |
| `behavior` | yes | all semantics; missing → `E_PARSE` |
| `behavior.interfaces` | recommended | empty I/O → useless rules |
| `behavior.parameters` | optional | only if rules need `$para.*` |
| `behavior.state` | optional | only if rules need `$state.*` / set_state |
| `behavior.timers` | optional | only if `on_timer` rules exist |
| `behavior.rules` | optional at parse | skill should warn if empty ("no behavior") |
| `interfaces.someip_tx` non-empty | allowed | `W_SOMEIP_IGNORED`; no codegen |

## Naming

- `ecu_mock.name`: PascalCase convention (`DoorECU`)
- Generated package dir: snake_case (`door_ecu`)
- Class name: as written (`DoorECU`)
- No file-stem fallback — name comes only from YAML

## Related errors

`E_PARSE`, `E_MISSING_ECU_NAME`
