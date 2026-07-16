"""IR stubs — SymbolKind / Symbol for symbol table; expanded in later tasks."""

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
