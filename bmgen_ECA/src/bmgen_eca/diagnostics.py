from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any

class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"

# Frozen public contract — do not rename codes without DESIGN_DECISIONS bump.
ERROR_CATALOG: dict[str, dict[str, Any]] = {
    "E_PARSE": {"code": "E_PARSE", "severity": Severity.ERROR, "when": "YAML load / bad shape", "help": "fix YAML to schema_v2 shape (apiVersion, ecu_mock.name, behavior)"},
    "E_MISSING_ECU_NAME": {"code": "E_MISSING_ECU_NAME", "severity": Severity.ERROR, "when": "missing ecu_mock.name", "help": "set ecu_mock.name"},
    "E_BAD_SIGNAL_ID": {"code": "E_BAD_SIGNAL_ID", "severity": Severity.ERROR, "when": "signal not [Bus]Frame.Signal", "help": "use [Bus]Frame.Signal form"},
    "E_DUP_SYMBOL": {"code": "E_DUP_SYMBOL", "severity": Severity.ERROR, "when": "duplicate param/state/timer/rule_id", "help": "rename so each provider/rule_id is unique"},
    "E_BARE_IDENT": {"code": "E_BARE_IDENT", "severity": Severity.ERROR, "when": "$name without state./para./[Bus]", "help": "use $state.x / $para.x / $[Bus]Frame.Signal"},
    "E_UNRESOLVED_IDENT": {"code": "E_UNRESOLVED_IDENT", "severity": Severity.ERROR, "when": "$ ref not in symbol table", "help": "declare provider or remove ref"},
    "E_UNKNOWN_FUNCTION": {"code": "E_UNKNOWN_FUNCTION", "severity": Severity.ERROR, "when": "call not min|max|abs", "help": "only min/max/abs allowed"},
    "E_TRIGGER_TARGET": {"code": "E_TRIGGER_TARGET", "severity": Severity.ERROR, "when": "bad on_rx/on_timer target", "help": "point trigger at declared can_rx or timer"},
    "E_TX_TARGET_NOT_IN_CAN_TX": {"code": "E_TX_TARGET_NOT_IN_CAN_TX", "severity": Severity.ERROR, "when": "tx target not in can_tx", "help": "add to interfaces.can_tx or fix target"},
    "E_SET_STATE_UNKNOWN": {"code": "E_SET_STATE_UNKNOWN", "severity": Severity.ERROR, "when": "set_state target not in state", "help": "add to state or fix target"},
    "E_BAD_EXPR": {"code": "E_BAD_EXPR", "severity": Severity.ERROR, "when": "expr syntax / ops outside MVP", "help": "see expr surface: $state/$para/$[Bus]Frame.Signal, + - * /, min/max/abs"},
    "E_BAD_ACTION": {"code": "E_BAD_ACTION", "severity": Severity.ERROR, "when": "action.type not tx|set_state", "help": "use tx or set_state"},
    "E_BAD_TRIGGER_TYPE": {"code": "E_BAD_TRIGGER_TYPE", "severity": Severity.ERROR, "when": "trigger.type not on_rx|on_timer", "help": "use on_rx or on_timer"},
    "E_MISSING_INIT": {"code": "E_MISSING_INIT", "severity": Severity.ERROR, "when": "state missing init", "help": "provide init"},
    "E_BAD_TIMER_INTERVAL": {"code": "E_BAD_TIMER_INTERVAL", "severity": Severity.ERROR, "when": "interval not positive number", "help": "interval > 0 float seconds"},
    "E_MULTI_BUS_UNSUPPORTED": {"code": "E_MULTI_BUS_UNSUPPORTED", "severity": Severity.ERROR, "when": ">1 bus in interfaces", "help": "single bus only in MVP"},
    "W_UNUSED_PARAM": {"code": "W_UNUSED_PARAM", "severity": Severity.WARNING, "when": "param never referenced", "help": "ok if documentation-only"},
    "W_UNUSED_STATE": {"code": "W_UNUSED_STATE", "severity": Severity.WARNING, "when": "state never read/written", "help": "remove or use"},
    "W_UNUSED_TIMER": {"code": "W_UNUSED_TIMER", "severity": Severity.WARNING, "when": "timer never on_timer target", "help": "remove or add rule"},
    "W_SOMEIP_IGNORED": {"code": "W_SOMEIP_IGNORED", "severity": Severity.WARNING, "when": "non-empty someip_tx", "help": "MVP does not codegen SOME/IP"},
}

def all_codes() -> set[str]:
    return set(ERROR_CATALOG)

@dataclass(frozen=True, order=True)
class Diag:
    severity: Severity
    code: str
    message: str
    path: str = ""
    rule_id: str = ""
    symbol: str = ""
    help: str = ""

    def sort_key(self) -> tuple[str, str, str, str]:
        return (self.path, self.rule_id, self.code, self.symbol)

def make_diag(code: str, message: str, *, path: str = "", rule_id: str = "", symbol: str = "") -> Diag:
    meta = ERROR_CATALOG[code]
    return Diag(
        severity=meta["severity"],
        code=code,
        message=message,
        path=path,
        rule_id=rule_id,
        symbol=symbol,
        help=meta["help"],
    )

def format_diag(d: Diag) -> str:
    head = f"{d.severity.value}[{d.code}]: {d.message}"
    loc_bits = []
    if d.path:
        loc_bits.append(d.path)
    if d.rule_id:
        loc_bits.append(f"rule={d.rule_id}")
    if d.symbol:
        loc_bits.append(f"symbol={d.symbol}")
    lines = [head]
    if loc_bits:
        lines.append(f"  --> {'  '.join(loc_bits)}")
    if d.help:
        lines.append(f"  help: {d.help}")
    return "\n".join(lines)

def sort_diags(diags: list[Diag]) -> list[Diag]:
    return sorted(diags, key=lambda d: d.sort_key())

def format_report_footer(diags: list[Diag]) -> str:
    errors = sum(1 for d in diags if d.severity == Severity.ERROR)
    warnings = sum(1 for d in diags if d.severity == Severity.WARNING)
    if errors:
        return f"error: aborting due to {errors} errors; {warnings} warnings; no code generated"
    return f"ok: {warnings} warnings"

def has_errors(diags: list[Diag]) -> bool:
    return any(d.severity == Severity.ERROR for d in diags)
