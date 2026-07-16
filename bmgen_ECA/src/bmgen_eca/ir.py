"""IR types — SymbolKind/Symbol for symbol table; RuleIR for resolved rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from bmgen_eca.signals import SignalId


class SymbolKind(str, Enum):
    RX = "rx"
    TX = "tx"
    PARAM = "param"
    STATE = "state"
    TIMER = "timer"


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: SymbolKind
    type_name: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    signal_id: SignalId | None = None


@dataclass(frozen=True)
class OnRx:
    signal: SignalId


@dataclass(frozen=True)
class OnTimer:
    timer_name: str


@dataclass(frozen=True)
class ActionIR:
    kind: str  # "set_state" | "tx"
    target_name: str  # state name or signal raw
    payload: Any  # ExprAST


@dataclass(frozen=True)
class RuleIR:
    rule_id: str
    trigger: OnRx | OnTimer
    condition: Any  # ExprAST
    actions: list[ActionIR]
    source_order: int


@dataclass(frozen=True)
class ResolvedModel:
    rules: list[RuleIR]
    ecu_name: str = ""
