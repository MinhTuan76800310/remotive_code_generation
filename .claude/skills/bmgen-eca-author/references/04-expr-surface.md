# Expression surface

## Allowed references

| Form | Resolves to |
|------|-------------|
| `$state.<name>` | STATE |
| `$para.<name>` | PARAM |
| `$[Bus]Frame.Signal` | can_rx entry (exact raw) |
| bare `$name` | **invalid** → `E_BARE_IDENT` |

## Operators

- Arithmetic: `+` `-` `*` `/`
- Unary: `-`
- Compare: `==` `!=` `>` `>=` `<` `<=`
- Boolean: `and` `or`
- Grouping: `( … )`
- Literals: numbers, `true` / `false`

## Functions (only)

| Call | Notes |
|------|-------|
| `min(a, b, …)` | ≥1 args; lowered with numpy in generated code |
| `max(a, b, …)` | same |
| `abs(x)` | one arg |

Anything else → `E_UNKNOWN_FUNCTION`.

## Forbidden (MVP)

- Strings in expr
- Arbitrary Python
- Reading TX-only signals via `$[…]`
- Mixed nonsense types (compiler may reject via `E_BAD_EXPR`)

## Examples

```text
true
abs($state.target_pos - $state.current_pos) > $para.pos_tolerance
max($para.min_pos, min($para.max_pos, $[DoorECU-BodyCan0]DoorCmd.TargetPosition))
$state.current_pos + max(0 - $para.move_step, min($para.move_step, $state.target_pos - $state.current_pos))
```
