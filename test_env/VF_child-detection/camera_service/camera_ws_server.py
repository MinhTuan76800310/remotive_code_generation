"""Camera child-detection websocket server + optional interactive web UI.

Two ports:
  1122  — WebSocket server. Both the DMS ECU and the browser UI connect here.
           - DMS ECU: connects and listens for broadcasts (two fields).
           - Browser UI: connects and sends button presses to change values.
           The server broadcasts the current state to ALL connected clients
           after each change. Each broadcast JSON payload includes BOTH
           fields; receivers pick which one(s) they care about.

  1123  — HTTP server (only when --ui is passed). Serves the interactive
           web page. Open http://localhost:1123 in your browser to control
           the camera simulation.

Two independent toggles (each 0 or 1):
  ChildDetected  — "is the camera confident a child is present?"
                   weight 0.7 in CENTRAL's CAD_logic.
  IsMoving       — "is the (presumed child) moving on the seat?"
                   weight 0.3 in CENTRAL's CAD_logic (motion amplifier).
  Both default to 0; --auto toggles ChildDetected every 2s, leaves
  IsMoving at 0. --ui lets the user toggle both via buttons.

Usage:
    uv run camera_ws_server.py --ui           # interactive web UI (browse to localhost:1123)
    uv run camera_ws_server.py --value 1     # continuously emit ChildDetected=1, IsMoving=0
    uv run camera_ws_server.py --value 0     # continuously emit ChildDetected=0, IsMoving=0
    uv run camera_ws_server.py --auto         # auto-toggle ChildDetected every 2s
    uv run camera_ws_server.py --value 1 --moving 1   # both fixed at 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time

import websockets

logger = logging.getLogger("camera-ws")

# ─── Shared mutable state ────────────────────────────────────────────────────
# Accessed from multiple websocket handlers — all access is inside async tasks.
_state: dict = {
    "ChildDetected": 0,
    "IsMoving": 0,
    "confidence": 0.10,
    "source": "passenger-camera-sim",
}

# All connected clients (both DMS ECU and browser UI) — we treat them identically
# after connection: both receive broadcasts, both can send updates.
_clients: set = set()


# ─── Message builder ────────────────────────────────────────────────────────

def build_message(detected: int, moving: int) -> str:
    """Emit a single JSON payload containing BOTH fields.

    Either field can be 0 or 1. Receivers that only care about one field
    ignore the other. The DMS ECU cares about both.
    """
    return json.dumps({
        "ChildDetected": int(detected),
        "IsMoving": int(moving),
        "confidence": 0.95 if detected else 0.10,
        "source": "passenger-camera-sim",
        "timestamp": int(time.time()),
    })


def broadcast(msg: str, exclude=None) -> None:
    """Fan-out a message to all connected clients."""
    if not _clients:
        return
    asyncio.create_task(_do_broadcast(msg, exclude))


async def _do_broadcast(msg: str, exclude):
    await asyncio.gather(
        *[ws.send(msg) for ws in list(_clients) if ws is not exclude],
        return_exceptions=True,
    )


# ─── Shared WebSocket handler (port 1122) ───────────────────────────────────
# Called for every new WebSocket connection — both the DMS ECU and the browser UI.

async def ws_handler(websocket):
    _clients.add(websocket)
    remote = websocket.remote_address
    logger.info("client connected: %s (%d total)", remote, len(_clients))

    # Send current state immediately so freshly-connected clients sync up.
    await websocket.send(build_message(_state["ChildDetected"], _state["IsMoving"]))

    try:
        async for raw in websocket:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue

            # Each field is independently toggleable. Receivers may send one
            # or both fields in any single message; unspecified fields keep
            # their current state.
            changed = False
            if "ChildDetected" in payload:
                new_cd = int(payload["ChildDetected"])
                if new_cd != _state["ChildDetected"]:
                    _state["ChildDetected"] = new_cd
                    changed = True
            if "IsMoving" in payload:
                new_mv = int(payload["IsMoving"])
                if new_mv != _state["IsMoving"]:
                    _state["IsMoving"] = new_mv
                    changed = True

            if changed:
                msg = build_message(_state["ChildDetected"], _state["IsMoving"])
                logger.info("state changed: ChildDetected=%s IsMoving=%s",
                            _state["ChildDetected"], _state["IsMoving"])
                await _do_broadcast(msg, exclude=None)

    except websockets.ConnectionClosed:
        pass
    finally:
        _clients.discard(websocket)
        logger.info("client disconnected: %s (%d remain)", remote, len(_clients))


# ─── Periodic broadcaster (non-UI modes) ────────────────────────────────────

async def broadcaster(interval: float, mode: str, fixed_detected: int, fixed_moving: int):
    """Auto-mode toggles ONLY ChildDetected (every 2s); IsMoving stays at 0.

    This keeps test scenarios deterministic: integration tests inject IsMoving
    directly via the broker's restbus on DMS-CpdCan0, not via this WS service.
    """
    tick = 0
    while True:
        detected = (tick % 2) if mode == "auto" else fixed_detected
        moving = 0 if mode == "auto" else fixed_moving
        _state["ChildDetected"] = detected
        _state["IsMoving"] = moving
        msg = build_message(detected, moving)
        if _clients:
            await _do_broadcast(msg, exclude=None)
            logger.info("broadcast ChildDetected=%s IsMoving=%s → %d client(s)",
                        detected, moving, len(_clients))
        tick += 1
        await asyncio.sleep(interval)


# ─── HTTP web UI (port 1123) ─────────────────────────────────────────────────

_UI_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Camera Child Detection</title>
<style>
  *,*::before,*::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', Arial, sans-serif;
    background: #0f1117;
    color: #e0e6f0;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1.5rem;
    padding: 2rem;
  }
  h1 { font-size: 1.4rem; font-weight: 600; color: #7dd3fc; letter-spacing: .02em; }

  .card {
    background: #1a1f2e;
    border: 1px solid #2a3142;
    border-radius: 18px;
    padding: 2rem 2.5rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1.4rem;
    width: 380px;
    box-shadow: 0 8px 32px rgba(0,0,0,.45);
  }

  .conn {
    font-size: .82rem;
    padding: .35rem .9rem;
    border-radius: 99px;
    background: #111827;
    border: 1px solid #1f2937;
  }
  .conn.ok   { color: #4ade80; border-color: #166534; }
  .conn.bad  { color: #f87171; border-color: #7f1d1d; }
  .conn.info { color: #fbbf24; border-color: #78350f; }

  .status-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: .8rem;
    width: 100%;
  }
  .status-tile {
    padding: .8rem;
    border-radius: 10px;
    text-align: center;
    font-size: 1.1rem;
    font-weight: 700;
    transition: background .25s, color .25s;
    background: #0f172a;
    color: #475569;
  }
  .status-tile.on {
    background: #450a0a;
    color: #fca5a5;
  }
  .status-tile.on.move {
    background: #78350f;
    color: #fbbf24;
  }
  .status-label {
    font-size: .68rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: .08em;
    color: #64748b;
    margin-bottom: .25rem;
  }

  .button-group { display: flex; gap: .8rem; width: 100%; }
  button {
    flex: 1;
    padding: .85rem .5rem;
    border: none;
    border-radius: 10px;
    font-size: .95rem;
    font-weight: 600;
    cursor: pointer;
    transition: transform .1s, box-shadow .15s;
  }
  button:active { transform: scale(.95); }
  .btn-red    { background: #dc2626; color: #fff; box-shadow: 0 4px 16px rgba(220,38,38,.35); }
  .btn-red:hover    { background: #b91c1c; }
  .btn-amber  { background: #d97706; color: #fff; box-shadow: 0 4px 16px rgba(217,119,6,.35); }
  .btn-amber:hover  { background: #b45309; }
  .btn-gray   { background: #1e293b; color: #94a3b8; border: 2px solid #334155; box-shadow: none; }
  .btn-gray:hover   { background: #263245; }

  .group-label {
    width: 100%;
    font-size: .72rem;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: .08em;
    text-align: center;
    margin-top: .4rem;
  }

  .info {
    width: 100%;
    font-size: .78rem;
    color: #475569;
    text-align: center;
    line-height: 1.5;
  }
</style>
</head>
<body>

<h1>Camera Child Detection</h1>

<div class="card">
  <div id="conn" class="conn info">● Connecting to camera service…</div>

  <div class="status-grid">
    <div class="status-tile" id="cdTile">
      <div class="status-label">Child Detected</div>
      <div id="cdVal">NO</div>
    </div>
    <div class="status-tile" id="mvTile">
      <div class="status-label">Is Moving</div>
      <div id="mvVal">NO</div>
    </div>
  </div>

  <div class="group-label">— Camera Confidence —</div>
  <div class="button-group">
    <button id="cdBtn1" class="btn-red">Child</button>
    <button id="cdBtn0" class="btn-gray">No Child</button>
  </div>

  <div class="group-label">— Motion Sensor —</div>
  <div class="button-group">
    <button id="mvBtn1" class="btn-amber">Moving</button>
    <button id="mvBtn0" class="btn-gray">Still</button>
  </div>

  <div class="info">Each field is independently toggled. The DMS ECU consumes
  both via the websocket; CENTRAL's CAD_logic uses weights [0.7, 0.3] and
  threshold 1.0.</div>
</div>

<script>
  const WS_PORT = 1122;
  let ws = null;
  const $ = id => document.getElementById(id);

  const cdTile = $('cdTile'), mvTile = $('mvTile');
  const cdVal  = $('cdVal'),  mvVal  = $('mvVal');
  const cdBtn1 = $('cdBtn1'), cdBtn0 = $('cdBtn0');
  const mvBtn1 = $('mvBtn1'), mvBtn0 = $('mvBtn0');
  const connEl = $('conn');

  function setValue(field, v) {
    if (field === 'ChildDetected') {
      cdVal.textContent = v ? 'YES' : 'NO';
      cdTile.className = 'status-tile' + (v ? ' on' : '');
      cdBtn1.style.boxShadow = v ? '0 0 0 3px #dc2626, 0 4px 16px rgba(220,38,38,.5)' : 'none';
      cdBtn0.style.boxShadow = v ? 'none' : '0 0 0 3px #334155';
    } else {
      mvVal.textContent = v ? 'YES' : 'NO';
      mvTile.className = 'status-tile' + (v ? ' on move' : '');
      mvBtn1.style.boxShadow = v ? '0 0 0 3px #d97706, 0 4px 16px rgba(217,119,6,.5)' : 'none';
      mvBtn0.style.boxShadow = v ? 'none' : '0 0 0 3px #334155';
    }
  }

  function send(field, v) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const msg = { [field]: v };
    ws.send(JSON.stringify(msg));
  }

  function connect() {
    ws = new WebSocket('ws://localhost:' + WS_PORT);
    connEl.textContent = '● Connecting…';
    connEl.className = 'conn info';

    ws.onopen = () => {
      connEl.textContent = '● Connected to camera service';
      connEl.className = 'conn ok';
    };

    ws.onmessage = e => {
      let d;
      try { d = JSON.parse(e.data); } catch { return; }
      if ('ChildDetected' in d) setValue('ChildDetected', d.ChildDetected);
      if ('IsMoving' in d)      setValue('IsMoving',      d.IsMoving);
    };

    ws.onclose = () => {
      connEl.textContent = '● Disconnected — retrying in 2s';
      connEl.className = 'conn bad';
      setTimeout(connect, 2000);
    };

    ws.onerror = () => ws.close();
  }

  cdBtn1.addEventListener('click', () => send('ChildDetected', 1));
  cdBtn0.addEventListener('click', () => send('ChildDetected', 0));
  mvBtn1.addEventListener('click', () => send('IsMoving', 1));
  mvBtn0.addEventListener('click', () => send('IsMoving', 0));

  connect();
</script>
</body>
</html>
"""


async def run_http(port: int):
    """HTTP server serving the interactive UI on port `port`."""
    import aiohttp.web
    app = aiohttp.web.Application()
    app.router.add_get("/", lambda _: aiohttp.web.Response(
        text=_UI_HTML, content_type="text/html", charset="utf-8"))
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Web UI: open http://localhost:%d in your browser", port)


# ─── Entrypoint ──────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Camera child-detection WS server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=1122, help="WebSocket port (DMS ECU + browser UI)")
    parser.add_argument("--ui-port", type=int, default=1123, help="HTTP web UI port (open in browser)")
    parser.add_argument("--interval", type=float, default=2.0)
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--value", type=int, choices=[0, 1], help="Fixed ChildDetected value (non-UI modes)")
    g.add_argument("--auto", action="store_true")
    g.add_argument("--ui", action="store_true")
    parser.add_argument("--moving", type=int, choices=[0, 1], default=0,
                        help="Fixed IsMoving value (non-UI modes; default 0)")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.value is not None:
        mode = "fixed"
        fixed_detected = args.value
        fixed_moving = args.moving
    elif args.ui:
        mode = "ui"
        fixed_detected = 0
        fixed_moving = 0
    else:
        mode = "auto"
        fixed_detected = 0
        fixed_moving = 0

    logger.info("Starting — WS on ws://%s:%s  mode=%s  moving=%s",
                args.host, args.port, mode,
                (fixed_moving if mode != "auto" else "auto-static-0"))
    if mode == "ui":
        logger.info("Web UI → open http://localhost:%s in your browser", args.ui_port)

    tasks = []

    if mode == "ui":
        tasks.append(run_http(args.ui_port))

    if mode == "auto" or mode == "fixed":
        tasks.append(broadcaster(args.interval, mode, fixed_detected, fixed_moving))

    async with websockets.serve(ws_handler, args.host, args.port):
        if tasks:
            await asyncio.gather(*tasks, asyncio.shield(asyncio.Future()))
        else:
            await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
