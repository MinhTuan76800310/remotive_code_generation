# Value domains (allowed attribute values)

| Attribute | Allowed | Error if wrong |
|-----------|---------|----------------|
| `apiVersion` | string (use `v1.0`) | shape/`E_PARSE` if root broken |
| `ecu_mock.name` | non-empty string | `E_MISSING_ECU_NAME` |
| signal id | `^\[([^\]]+)\]([^.]+)\.(.+)$` | `E_BAD_SIGNAL_ID` |
| param/state `type` | `bool` \| `int` \| `float` | parse/semantic issues |
| param `value` | matches type | |
| state `init` | matches type; **required** | `E_MISSING_INIT` |
| timer `interval` | number > 0 | `E_BAD_TIMER_INTERVAL` |
| timer `auto_start` | bool | |
| `trigger.type` | `on_rx` \| `on_timer` | `E_BAD_TRIGGER_TYPE` |
| `action.type` | `set_state` \| `tx` | `E_BAD_ACTION` |
| expr functions | `min` \| `max` \| `abs` | `E_UNKNOWN_FUNCTION` |
| buses in one ECU | **exactly one** distinct bus | `E_MULTI_BUS_UNSUPPORTED` |
| duplicate names | not allowed (param/state/timer/rule_id) | `E_DUP_SYMBOL` |

## Signal id anatomy

```text
[DoorECU-BodyCan0]DoorCmd.TargetPosition
 └────── bus ──────┘└frame┘└── signal ──┘
```

- Bus string becomes Remotive `CanNamespace` name in generated code.
- Frame groups handlers: one handler per `(bus, frame)`.
