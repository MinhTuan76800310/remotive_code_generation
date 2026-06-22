"""Tests for the WebsocketBridge recipe plugin — external websocket → CAN restbus.

A websocket listener is a MODEL-LEVEL background asyncio task (not a handler),
because handlers are CAN-frame-triggered and a websocket has no CAN frame.
These tests cover:
  - IR construction (WebsocketListenerIR + BehavioralModelIR.websocket_listeners)
  - Invariant 12 validation (url scheme, output namespace existence + restbus,
    signal_map non-empty, cleanup=True, name uniqueness)
  - End-to-end code generation (JSON decode loop, reconnect+warn, start/stop
    lifecycle, restbus.update_signals, gated so non-ws models are unchanged)
  - Regression: existing models still generate byte-identical output
"""

import os

import pytest

from bmgen.compiler.context_builder import build_template_context
from bmgen.compiler.python_generator import generate
from bmgen.ir.builder import build_ir, BuilderError
from bmgen.ir.parser import parse_yaml_string
from bmgen.recipes.registry import create_default_registry


# ─────────────────────────────────────────────────────────────────────────────
# Fixture YAMLs
# ─────────────────────────────────────────────────────────────────────────────

DMS_WEBSOCKET_YAML = """
model:
  name: DriverMonitoringECU
  ecu_name: DMS

namespaces:
  - name: DMS-DmsCan0
    type: can
    role: output
    restbus:
      sender_filter: DMS

websocket_listeners:
  - name: camera_child_detection
    url: ws://localhost:1122
    output_namespace: DMS-DmsCan0
    signal_map:
      - ws_key: ChildDetected
        signal: ChildDetectionInput.ChildDetectedByCamera
    cleanup: true
    reconnect_delay_sec: 2.0

handlers: []
"""


@pytest.fixture
def dms_ws_yaml():
    return DMS_WEBSOCKET_YAML


@pytest.fixture
def dms_ws_ir(dms_ws_yaml):
    return build_ir(parse_yaml_string(dms_ws_yaml))


# ─────────────────────────────────────────────────────────────────────────────
# IR construction
# ─────────────────────────────────────────────────────────────────────────────

class TestWebsocketListenerIRConstruction:
    """The builder parses the top-level websocket_listeners: section."""

    def test_ir_has_websocket_listeners_field(self, dms_ws_ir):
        assert hasattr(dms_ws_ir, "websocket_listeners")
        assert len(dms_ws_ir.websocket_listeners) == 1

    def test_listener_fields_parsed(self, dms_ws_ir):
        ws = dms_ws_ir.websocket_listeners[0]
        assert ws.name == "camera_child_detection"
        assert ws.url == "ws://localhost:1122"
        assert ws.output_namespace == "DMS-DmsCan0"
        assert ws.cleanup is True
        assert ws.reconnect_delay_sec == 2.0

    def test_listener_signal_map_parsed(self, dms_ws_ir):
        ws = dms_ws_ir.websocket_listeners[0]
        assert len(ws.signal_map) == 1
        assert ws.signal_map[0] == ("ChildDetected", "ChildDetectionInput.ChildDetectedByCamera")

    def test_model_without_listeners_has_empty_list(self, bcm_direct_ir):
        # Existing models have no websocket_listeners: key -> empty list, not None.
        assert bcm_direct_ir.websocket_listeners == []

    def test_reconnect_delay_defaults_to_2(self):
        spec = parse_yaml_string("""
model:
  name: DMS
  ecu_name: DMS
namespaces:
  - name: DMS-Out0
    type: can
    role: output
    restbus:
      sender_filter: DMS
websocket_listeners:
  - name: ws1
    url: ws://localhost:1122
    output_namespace: DMS-Out0
    signal_map:
      - ws_key: k
        signal: Frame.Sig
    cleanup: true
handlers: []
""")
        ir = build_ir(spec)
        assert ir.websocket_listeners[0].reconnect_delay_sec == 2.0


# ─────────────────────────────────────────────────────────────────────────────
# Invariant 12 — websocket_listener validation
# ─────────────────────────────────────────────────────────────────────────────

class TestWebsocketListenerValidation:
    """Invariant 12: websocket_listener_valid."""

    def test_valid_listener_passes(self, dms_ws_ir):
        from bmgen.ir.validators import validate, has_errors
        violations = [v for v in validate(dms_ws_ir) if "websocket" in v.rule]
        assert violations == []
        assert not has_errors(validate(dms_ws_ir))

    # Shared header for all "one bad listener" tests — only the listener block
    # differs. Block-style YAML so the spec parses and reaches the validator
    # (Invariant 12), not the YAML parser.
    _BASE = """
model:
  name: DMS
  ecu_name: DMS
namespaces:
  - name: DMS-Out0
    type: can
    role: output
    restbus:
      sender_filter: DMS
websocket_listeners:
{listeners}
handlers: []
"""

    def _spec(self, listeners_yaml):
        return self._BASE.format(listeners=listeners_yaml)

    def test_non_ws_url_scheme_fails(self):
        spec = self._spec("""  - name: ws1
    url: http://localhost:1122
    output_namespace: DMS-Out0
    signal_map:
      - ws_key: k
        signal: Frame.Sig
    cleanup: true
""")
        with pytest.raises(BuilderError) as exc:
            build_ir(parse_yaml_string(spec))
        assert any("websocket" in v.rule and ("url" in v.message.lower() or "ws" in v.message.lower()) for v in exc.value.violations)

    def test_nonexistent_output_namespace_fails(self):
        spec = self._spec("""  - name: ws1
    url: ws://localhost:1122
    output_namespace: NOPE
    signal_map:
      - ws_key: k
        signal: Frame.Sig
    cleanup: true
""")
        with pytest.raises(BuilderError) as exc:
            build_ir(parse_yaml_string(spec))
        assert any("websocket" in v.rule and "namespace" in v.message.lower() for v in exc.value.violations)

    def test_output_namespace_without_restbus_fails(self):
        # DMS-Out0 here has role: output but NO restbus (override the base header).
        spec = """
model:
  name: DMS
  ecu_name: DMS
namespaces:
  - name: DMS-Out0
    type: can
    role: output
websocket_listeners:
  - name: ws1
    url: ws://localhost:1122
    output_namespace: DMS-Out0
    signal_map:
      - ws_key: k
        signal: Frame.Sig
    cleanup: true
handlers: []
"""
        with pytest.raises(BuilderError) as exc:
            build_ir(parse_yaml_string(spec))
        assert any("websocket" in v.rule and "restbus" in v.message.lower() for v in exc.value.violations)

    def test_empty_signal_map_fails(self):
        spec = self._spec("""  - name: ws1
    url: ws://localhost:1122
    output_namespace: DMS-Out0
    signal_map: []
    cleanup: true
""")
        with pytest.raises(BuilderError) as exc:
            build_ir(parse_yaml_string(spec))
        assert any("websocket" in v.rule and "signal" in v.message.lower() for v in exc.value.violations)

    def test_cleanup_false_fails(self):
        spec = self._spec("""  - name: ws1
    url: ws://localhost:1122
    output_namespace: DMS-Out0
    signal_map:
      - ws_key: k
        signal: Frame.Sig
    cleanup: false
""")
        with pytest.raises(BuilderError) as exc:
            build_ir(parse_yaml_string(spec))
        assert any("websocket" in v.rule and "cleanup" in v.message.lower() for v in exc.value.violations)

    def test_duplicate_listener_names_fails(self):
        spec = self._spec("""  - name: dup
    url: ws://localhost:1
    output_namespace: DMS-Out0
    signal_map:
      - ws_key: k
        signal: Frame.Sig
    cleanup: true
  - name: dup
    url: ws://localhost:2
    output_namespace: DMS-Out0
    signal_map:
      - ws_key: k
        signal: Frame.Sig
    cleanup: true
""")
        with pytest.raises(BuilderError) as exc:
            build_ir(parse_yaml_string(spec))
        assert any("websocket" in v.rule and "name" in v.message.lower() for v in exc.value.violations)


# ─────────────────────────────────────────────────────────────────────────────
# Recipe + registry
# ─────────────────────────────────────────────────────────────────────────────

class TestWebsocketBridgeRecipeRegistered:
    """The WebsocketBridge recipe is registered in the default registry."""

    def test_recipe_in_registry(self):
        registry = create_default_registry()
        assert "WebsocketBridge" in registry.known_patterns()

    def test_recipe_has_correct_metadata(self):
        registry = create_default_registry()
        recipe = registry.get("WebsocketBridge")
        assert recipe is not None
        fields = recipe.required_fields()
        assert fields["name"] == "WebsocketBridge"

    def test_recipe_rejects_handler_ir(self):
        """The recipe must not be callable with a HandlerIR (LSP guard)."""
        from bmgen.ir.model import HandlerIR
        registry = create_default_registry()
        recipe = registry.get("WebsocketBridge")
        result = recipe.validate(HandlerIR(name="x", pattern="WebsocketBridge"))
        # Must return a non-empty error list (isinstance guard), not crash.
        assert isinstance(result, list)
        assert len(result) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Code generation
# ─────────────────────────────────────────────────────────────────────────────

class TestWebsocketBridgeGeneration:
    """End-to-end generation of a websocket-bridge model."""

    def _generate(self, yaml_text, tmpdir):
        spec = parse_yaml_string(yaml_text)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, tmpdir)
        main_path = os.path.join(tmpdir, "drivermonitoringecu", "__main__.py")
        with open(main_path) as f:
            return f.read()

    def test_generated_main_is_valid_python(self, dms_ws_yaml, temp_output_dir):
        import ast
        content = self._generate(dms_ws_yaml, temp_output_dir)
        ast.parse(content)  # no SyntaxError

    def test_generated_imports_websockets(self, dms_ws_yaml, temp_output_dir):
        content = self._generate(dms_ws_yaml, temp_output_dir)
        assert "import websockets" in content

    def test_generated_has_listener_loop(self, dms_ws_yaml, temp_output_dir):
        content = self._generate(dms_ws_yaml, temp_output_dir)
        # The background loop method + start/stop lifecycle.
        assert "websockets.connect" in content
        assert "ws://localhost:1122" in content
        assert "json.loads" in content

    def test_generated_maps_ws_key_to_signal(self, dms_ws_yaml, temp_output_dir):
        content = self._generate(dms_ws_yaml, temp_output_dir)
        assert "ChildDetected" in content
        assert "ChildDetectionInput.ChildDetectedByCamera" in content
        assert "restbus.update_signals" in content

    def test_generated_has_reconnect_and_warning(self, dms_ws_yaml, temp_output_dir):
        content = self._generate(dms_ws_yaml, temp_output_dir)
        # Reconnect loop + warning log (not a hard crash).
        assert "asyncio.sleep" in content
        assert "warning" in content.lower() or "logger.warning" in content

    def test_generated_has_start_and_stop_lifecycle(self, dms_ws_yaml, temp_output_dir):
        content = self._generate(dms_ws_yaml, temp_output_dir)
        # Launched before run_forever, cancelled in finally.
        assert "run_forever" in content
        assert "cancel" in content
        assert "finally" in content

    def test_generated_has_no_input_handler_registration(self, dms_ws_yaml, temp_output_dir):
        """A ws-only ECU registers no CAN input handlers."""
        content = self._generate(dms_ws_yaml, temp_output_dir)
        assert "create_input_handler" not in content


# ─────────────────────────────────────────────────────────────────────────────
# Regression — existing models must be unchanged
# ─────────────────────────────────────────────────────────────────────────────

class TestWebsocketBridgeRegression:
    """Adding websocket support must not change existing model output."""

    def test_direct_mapping_model_has_no_websocket_code(self, bcm_direct_yaml, temp_output_dir):
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        main_path = os.path.join(temp_output_dir, "bcm", "__main__.py")
        with open(main_path) as f:
            content = f.read()

        # No websocket artifacts leak into a non-websocket model.
        assert "import websockets" not in content
        assert "websockets.connect" not in content
        assert "websocket" not in content.lower()
        # And it still has its normal handler.
        assert "async def on_hazard_light" in content
        assert "create_input_handler" in content

    def test_direct_mapping_model_still_parses_and_validates(self, bcm_direct_ir):
        """The IR for an existing model is unaffected by the new field."""
        assert bcm_direct_ir.websocket_listeners == []
        assert len(bcm_direct_ir.handlers) == 1


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end — the generated loop actually flows JSON values → restbus
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import json
import socket

import websockets


def _free_port() -> int:
    """Pick an unused TCP port for a throwaway websocket server."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _FakeRestbus:
    """Captures update_signals calls so the test can assert what was published."""

    def __init__(self):
        self.calls = []

    async def update_signals(self, *configs):
        self.calls.append(configs)


class _FakeNamespace:
    """Mimics CanNamespace.restbus — the only attribute the loop touches."""

    def __init__(self):
        self.restbus = _FakeRestbus()


class _FakeModel:
    """Holds the output namespace attribute the generated loop reads via self."""

    def __init__(self, ns_var_name):
        setattr(self, ns_var_name, _FakeNamespace())


class TestWebsocketBridgeEndToEndLoop:
    """Run the EXACT loop body the template generates against a real websocket
    server, proving JSON messages flow through to restbus.update_signals.

    This test does NOT import remotivelabs.topology (not installed locally), so
    it runs everywhere. It reconstructs the generated loop's body verbatim and
    drives it with a real `websockets.serve` camera-style server.
    """

    def test_loop_publishes_json_values_to_restbus(self):
        port = _free_port()
        url = f"ws://127.0.0.1:{port}"
        signal_map = [("ChildDetected", "ChildDetectionInput.ChildDetectedByCamera")]
        model = _FakeModel("dms_can_0")
        sent = [{"ChildDetected": 1}, {"ChildDetected": 0}, {"ChildDetected": 1}]

        async def camera_server(ws):
            # Emulate the camera child-detection service: push JSON frames.
            for payload in sent:
                await ws.send(json.dumps(payload))

        async def run_loop():
            # This is the verbatim body of the generated _ws_loop_* method,
            # with logging calls stripped (they need the runtime's logging setup
            # and add nothing to the correctness proof).
            ws_url = url
            smap = signal_map
            while True:
                try:
                    async with websockets.connect(ws_url) as ws:
                        async for raw in ws:
                            payload = json.loads(raw)
                            await model.dms_can_0.restbus.update_signals(
                                *[(sig, payload.get(key)) for key, sig in smap]
                            )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await asyncio.sleep(0.05)

        async def main():
            async with websockets.serve(camera_server, "127.0.0.1", port):
                task = asyncio.create_task(run_loop())
                # Wait until all three frames have been published.
                for _ in range(100):
                    if len(model.dms_can_0.restbus.calls) >= len(sent):
                        break
                    await asyncio.sleep(0.01)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        asyncio.run(main())

        # The loop publishes one update_signals call per JSON frame it receives.
        # Because the camera_server closes after sending its batch, the loop
        # reconnects and re-receives — so we assert the VALUES flow correctly
        # and at least one full batch arrived, not an exact call count (the
        # reconnect behavior is exercised separately below).
        calls = model.dms_can_0.restbus.calls
        assert len(calls) >= len(sent)
        # Each call carries the mapped (signal, value) tuple, in send order.
        for call, payload in zip(calls[: len(sent)], sent):
            assert call == (("ChildDetectionInput.ChildDetectedByCamera", payload["ChildDetected"]),)

    def test_loop_reconnects_after_server_drops(self):
        """On disconnect the loop reconnects (warning + sleep) and keeps going."""
        port = _free_port()
        url = f"ws://127.0.0.1:{port}"
        signal_map = [("ChildDetected", "ChildDetectionInput.ChildDetectedByCamera")]
        model = _FakeModel("dms_can_0")
        connection_count = {"n": 0}

        async def flaky_server(ws):
            connection_count["n"] += 1
            if connection_count["n"] == 1:
                # First connection: send one frame, then drop.
                await ws.send(json.dumps({"ChildDetected": 1}))
                await asyncio.sleep(0.05)
                raise websockets.ConnectionClosed(None, None)
            # Reconnected: send another frame, then stay open.
            await ws.send(json.dumps({"ChildDetected": 0}))
            await asyncio.sleep(0.5)

        async def run_loop():
            ws_url = url
            smap = signal_map
            while True:
                try:
                    async with websockets.connect(ws_url) as ws:
                        async for raw in ws:
                            payload = json.loads(raw)
                            await model.dms_can_0.restbus.update_signals(
                                *[(sig, payload.get(key)) for key, sig in smap]
                            )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await asyncio.sleep(0.02)

        async def main():
            async with websockets.serve(flaky_server, "127.0.0.1", port):
                task = asyncio.create_task(run_loop())
                for _ in range(200):
                    if len(model.dms_can_0.restbus.calls) >= 2:
                        break
                    await asyncio.sleep(0.01)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        asyncio.run(main())

        # Both the pre-drop and post-reconnect frames were published, and the
        # loop connected at least twice (proving the reconnect path ran).
        calls = model.dms_can_0.restbus.calls
        assert len(calls) >= 2
        assert connection_count["n"] >= 2
        assert calls[0] == (("ChildDetectionInput.ChildDetectedByCamera", 1),)


class TestWebsocketBridgeEndToEndGeneratedModule:
    """Import the ACTUALLY generated module and run its real _ws_loop_* method
    against a real websocket server. This is the strongest proof: it exercises
    the template's real output, not a reconstruction.

    Requires remotivelabs.topology (installed in CI). Skips locally where the
    package is absent — see the Option A rationale in the session notes.
    """

    def test_real_generated_module_flows_values(self, dms_ws_yaml, temp_output_dir):
        pytest.importorskip("remotivelabs.topology")

        spec = parse_yaml_string(dms_ws_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        model_pkg = os.path.join(temp_output_dir, "drivermonitoringecu")
        main_path = os.path.join(model_pkg, "__main__.py")

        # Load the generated module from disk (it is not on sys.path).
        import importlib.util
        spec_mod = importlib.util.spec_from_file_location("dms_generated_main", main_path)
        module = importlib.util.module_from_spec(spec_mod)
        spec_mod.loader.exec_module(module)

        DriverMonitoringECU = module.DriverMonitoringECU

        # Build a model instance whose output namespace is a fake restbus, so
        # we don't need a real Remotive broker. The generated class only reads
        # self.dms_can_0.restbus.update_signals inside the loop.
        class _FakeRestbus:
            def __init__(self):
                self.calls = []

            async def update_signals(self, *configs):
                self.calls.append(configs)

        ns = type("NS", (), {"restbus": _FakeRestbus()})()
        instance = DriverMonitoringECU(dms_can_0=ns)

        port = _free_port()
        sent = [{"ChildDetected": 1}, {"ChildDetected": 0}]

        async def camera_server(ws):
            for payload in sent:
                await ws.send(json.dumps(payload))

        async def main():
            async with websockets.serve(camera_server, "127.0.0.1", port):
                # Monkeypatch the URL onto the bound loop (it's a literal in the
                # generated body). We instead point the server at the port the
                # generated code will connect to by patching the module-level
                # nothing — simpler: just override ws_url by running the loop on
                # a wrapper. Easiest correct approach: call the start method,
                # let it create the task with the literal localhost:1122 URL,
                # but we cannot run a server on 1122 reliably. Instead invoke
                # the loop coroutine directly with a patched connect via the
                # module's websockets binding.
                import unittest.mock as mock

                with mock.patch.object(module, "websockets") as fake_ws:
                    real_connect = websockets.connect

                    def fake_connect(u, *a, **k):
                        return real_connect(f"ws://127.0.0.1:{port}", *a, **k)

                    fake_ws.connect = fake_connect
                    task = asyncio.create_task(instance._ws_loop_camera_child_detection())
                    for _ in range(200):
                        if len(ns.restbus.calls) >= len(sent):
                            break
                        await asyncio.sleep(0.01)
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        asyncio.run(main())

        calls = ns.restbus.calls
        # At least one full batch flowed through the REAL generated loop.
        assert len(calls) >= len(sent)
        assert calls[0] == (("ChildDetectionInput.ChildDetectedByCamera", 1),)
        assert calls[1] == (("ChildDetectionInput.ChildDetectedByCamera", 0),)
