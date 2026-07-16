"""Build frozen SymbolTable from RawEcu providers (rx/tx/param/state/timer)."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from bmgen_eca.diagnostics import Diag, has_errors, make_diag, sort_diags
from bmgen_eca.ir import Symbol, SymbolKind
from bmgen_eca.parser import RawEcu
from bmgen_eca.signals import SignalId, parse_signal_id


@dataclass(frozen=True)
class SymbolTable:
    bus: str
    _rx: Mapping[str, Symbol]
    _tx: Mapping[str, Symbol]
    _params: Mapping[str, Symbol]
    _states: Mapping[str, Symbol]
    _timers: Mapping[str, Symbol]

    def lookup_state(self, name: str) -> Symbol | None:
        return self._states.get(name)

    def lookup_param(self, name: str) -> Symbol | None:
        return self._params.get(name)

    def lookup_timer(self, name: str) -> Symbol | None:
        return self._timers.get(name)

    def lookup_rx(self, raw_or_sid: str | SignalId) -> Symbol | None:
        key = raw_or_sid.raw if isinstance(raw_or_sid, SignalId) else raw_or_sid
        return self._rx.get(key)

    def lookup_tx(self, raw_or_sid: str | SignalId) -> Symbol | None:
        key = raw_or_sid.raw if isinstance(raw_or_sid, SignalId) else raw_or_sid
        return self._tx.get(key)


def build_symbols(raw: RawEcu) -> tuple[SymbolTable | None, list[Diag]]:
    diags: list[Diag] = []
    path = raw.path

    rx: dict[str, Symbol] = {}
    tx: dict[str, Symbol] = {}
    params: dict[str, Symbol] = {}
    states: dict[str, Symbol] = {}
    timers: dict[str, Symbol] = {}
    # Shared namespace for param/state/timer short names (and dup across them)
    short_names: dict[str, SymbolKind] = {}
    buses: set[str] = set()

    def _claim_short(name: str, kind: SymbolKind) -> bool:
        if name in short_names:
            diags.append(
                make_diag(
                    "E_DUP_SYMBOL",
                    f"duplicate symbol `{name}` ({kind.value}; already {short_names[name].value})",
                    path=path,
                    symbol=name,
                )
            )
            return False
        short_names[name] = kind
        return True

    # --- can_rx ---
    for sig in raw.can_rx:
        sid, d = parse_signal_id(sig, path=path)
        if d is not None:
            diags.append(d)
            continue
        assert sid is not None
        if sid.raw in rx:
            diags.append(
                make_diag(
                    "E_DUP_SYMBOL",
                    f"duplicate can_rx `{sid.raw}`",
                    path=path,
                    symbol=sid.raw,
                )
            )
            continue
        buses.add(sid.bus)
        rx[sid.raw] = Symbol(
            name=sid.raw,
            kind=SymbolKind.RX,
            signal_id=sid,
            meta={"signal_id": sid},
        )

    # --- can_tx ---
    for sig in raw.can_tx:
        sid, d = parse_signal_id(sig, path=path)
        if d is not None:
            diags.append(d)
            continue
        assert sid is not None
        if sid.raw in tx:
            diags.append(
                make_diag(
                    "E_DUP_SYMBOL",
                    f"duplicate can_tx `{sid.raw}`",
                    path=path,
                    symbol=sid.raw,
                )
            )
            continue
        buses.add(sid.bus)
        tx[sid.raw] = Symbol(
            name=sid.raw,
            kind=SymbolKind.TX,
            signal_id=sid,
            meta={"signal_id": sid},
        )

    if len(buses) > 1:
        diags.append(
            make_diag(
                "E_MULTI_BUS_UNSUPPORTED",
                f"multiple buses in interfaces: {sorted(buses)} (MVP single bus only)",
                path=path,
            )
        )

    # --- parameters ---
    for entry in raw.parameters:
        name = entry.get("name")
        if not name:
            continue
        name = str(name)
        if not _claim_short(name, SymbolKind.PARAM):
            continue
        params[name] = Symbol(
            name=name,
            kind=SymbolKind.PARAM,
            type_name=str(entry["type"]) if "type" in entry else None,
            meta={"value": entry.get("value")},
        )

    # --- state ---
    for entry in raw.state:
        name = entry.get("name")
        if not name:
            continue
        name = str(name)
        if "init" not in entry:
            diags.append(
                make_diag(
                    "E_MISSING_INIT",
                    f"state `{name}` missing init",
                    path=path,
                    symbol=name,
                )
            )
            # still claim name so later dups are detected
        if not _claim_short(name, SymbolKind.STATE):
            continue
        states[name] = Symbol(
            name=name,
            kind=SymbolKind.STATE,
            type_name=str(entry["type"]) if "type" in entry else None,
            meta={"init": entry.get("init")},
        )

    # --- timers ---
    for entry in raw.timers:
        name = entry.get("name")
        if not name:
            continue
        name = str(name)
        interval = entry.get("interval")
        if not isinstance(interval, (int, float)) or isinstance(interval, bool) or not (interval > 0):
            diags.append(
                make_diag(
                    "E_BAD_TIMER_INTERVAL",
                    f"timer `{name}` interval must be number > 0, got {interval!r}",
                    path=path,
                    symbol=name,
                )
            )
        if not _claim_short(name, SymbolKind.TIMER):
            continue
        timers[name] = Symbol(
            name=name,
            kind=SymbolKind.TIMER,
            meta={
                "interval": interval,
                "auto_start": entry.get("auto_start", False),
            },
        )

    diags = sort_diags(diags)
    if has_errors(diags):
        return None, diags

    bus = next(iter(buses)) if buses else ""
    table = SymbolTable(
        bus=bus,
        _rx=MappingProxyType(rx),
        _tx=MappingProxyType(tx),
        _params=MappingProxyType(params),
        _states=MappingProxyType(states),
        _timers=MappingProxyType(timers),
    )
    return table, diags
