"""YAML → RawEcu for schema_v2 (apiVersion + ecu_mock.name + behavior)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from bmgen_eca.diagnostics import Diag, make_diag


@dataclass
class RawEcu:
    ecu_name: str
    path: str
    can_rx: list[str] = field(default_factory=list)
    can_tx: list[str] = field(default_factory=list)
    someip_tx: list[str] = field(default_factory=list)
    parameters: list[dict] = field(default_factory=list)
    state: list[dict] = field(default_factory=list)
    timers: list[dict] = field(default_factory=list)
    rules: list[dict] = field(default_factory=list)


def _signal_names(entries: Any) -> list[str]:
    if not isinstance(entries, list):
        return []
    out: list[str] = []
    for item in entries:
        if isinstance(item, dict) and "signal" in item:
            out.append(str(item["signal"]))
        elif isinstance(item, str):
            out.append(item)
    return out


def _dict_list(entries: Any) -> list[dict]:
    if not isinstance(entries, list):
        return []
    return [item for item in entries if isinstance(item, dict)]


def parse_file(path: Path) -> tuple[RawEcu | None, list[Diag]]:
    path_str = str(path)
    try:
        data = yaml.safe_load(path.read_text())
    except Exception as e:
        return None, [make_diag("E_PARSE", f"YAML error: {e}", path=path_str)]

    if not isinstance(data, dict):
        return None, [make_diag("E_PARSE", "root must be mapping", path=path_str)]

    ecu_mock = data.get("ecu_mock") or {}
    name = ecu_mock.get("name") if isinstance(ecu_mock, dict) else None
    if not name:
        return None, [
            make_diag(
                "E_MISSING_ECU_NAME",
                "ecu_mock.name is required",
                path=path_str,
            )
        ]

    behavior = data.get("behavior")
    if not isinstance(behavior, dict):
        return None, [
            make_diag("E_PARSE", "behavior block required", path=path_str)
        ]

    ifaces = behavior.get("interfaces") or {}
    if not isinstance(ifaces, dict):
        ifaces = {}

    raw = RawEcu(
        ecu_name=str(name),
        path=path_str,
        can_rx=_signal_names(ifaces.get("can_rx")),
        can_tx=_signal_names(ifaces.get("can_tx")),
        someip_tx=_signal_names(ifaces.get("someip_tx")),
        parameters=_dict_list(behavior.get("parameters")),
        state=_dict_list(behavior.get("state")),
        timers=_dict_list(behavior.get("timers")),
        rules=_dict_list(behavior.get("rules")),
    )
    return raw, []
