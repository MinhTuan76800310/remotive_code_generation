# Errors → fix (hard-gate checklist)

Source of truth: `bmgen-eca errors` (frozen `ERROR_CATALOG`).

When parse fails: for each `E_*` line, apply the fix below, then re-run parse.

| Code | When | YAML fix |
|------|------|----------|
| `E_PARSE` | YAML load / bad shape | Fix YAML syntax; ensure root mapping with `apiVersion`, `ecu_mock`, `behavior` |
| `E_MISSING_ECU_NAME` | missing `ecu_mock.name` | Set `ecu_mock.name: YourEcu` |
| `E_BAD_SIGNAL_ID` | signal not `[Bus]Frame.Signal` | Rewrite to `[Bus]Frame.Signal` |
| `E_DUP_SYMBOL` | duplicate param/state/timer/rule_id | Rename to unique |
| `E_BARE_IDENT` | `$name` without prefix | Use `$state.x` / `$para.x` / `$[Bus]Frame.Signal` |
| `E_UNRESOLVED_IDENT` | `$` ref not declared | Declare provider or remove ref |
| `E_UNKNOWN_FUNCTION` | call not min\|max\|abs | Replace with min/max/abs only |
| `E_TRIGGER_TARGET` | bad on_rx/on_timer target | Point at declared can_rx raw or timer name |
| `E_TX_TARGET_NOT_IN_CAN_TX` | tx target missing | Add to `interfaces.can_tx` or fix target string |
| `E_SET_STATE_UNKNOWN` | set_state target missing | Add to `state` or fix name |
| `E_BAD_EXPR` | expr outside MVP | See `04-expr-surface.md` |
| `E_BAD_ACTION` | action.type invalid | Use `tx` or `set_state` |
| `E_BAD_TRIGGER_TYPE` | trigger.type invalid | Use `on_rx` or `on_timer` |
| `E_MISSING_INIT` | state without init | Add `init:` |
| `E_BAD_TIMER_INTERVAL` | interval not positive number | Set float/int seconds > 0 |
| `E_MULTI_BUS_UNSUPPORTED` | >1 bus | Use one bus name for all signals |

## Warnings (do not block DONE)

| Code | Meaning | Action |
|------|---------|--------|
| `W_UNUSED_PARAM` | param never referenced | remove or keep as doc |
| `W_UNUSED_STATE` | state never used | remove or use |
| `W_UNUSED_TIMER` | timer never targeted | remove or add rule |
| `W_SOMEIP_IGNORED` | someip_tx non-empty | OK for MVP; no codegen |

## Loop

```text
parse → E_*? → fix using this table + 03-field-graph → parse again
until zero errors
```
