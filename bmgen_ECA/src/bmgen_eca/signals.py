from __future__ import annotations
import re
from dataclasses import dataclass
from bmgen_eca.diagnostics import Diag, make_diag

_SIGNAL_RE = re.compile(r"^\[([^\]]+)\]([^.]+)\.(.+)$")


@dataclass(frozen=True)
class SignalId:
    bus: str
    frame: str
    signal: str
    raw: str

    @property
    def frame_key(self) -> tuple[str, str]:
        return (self.bus, self.frame)


def parse_signal_id(raw: str, *, path: str = "") -> tuple[SignalId | None, Diag | None]:
    m = _SIGNAL_RE.match(raw.strip())
    if not m or not m.group(1) or not m.group(2) or not m.group(3):
        return None, make_diag(
            "E_BAD_SIGNAL_ID",
            f"invalid signal id `{raw}` (want [Bus]Frame.Signal)",
            path=path,
            symbol=raw,
        )
    return SignalId(bus=m.group(1), frame=m.group(2), signal=m.group(3), raw=raw.strip()), None
