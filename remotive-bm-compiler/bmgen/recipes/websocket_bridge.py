"""WebsocketBridge recipe — bridge an external websocket stream onto a CAN restbus.

This is a MODEL-LEVEL recipe, not a per-handler recipe. A websocket listener
runs a long-running background asyncio task for the ECU's whole lifetime:
  - connect to ws://host:port
  - for each JSON message, map each ws_key → a restbus signal on the output
    namespace and call restbus.update_signals
  - on disconnect/error, log a warning and reconnect after reconnect_delay_sec
  - on exit/reboot, the task is cancelled (cleanup=True is enforced)

Why model-level, not a handler:
  Every handler in a Remotive behavioral model is triggered by an incoming CAN
  frame (create_input_handler + FrameFilter). A websocket has no CAN frame, so
  it cannot be a handler. The listener is launched in main() inside the
  BehavioralModel context, before run_forever(), and cancelled in a finally.

The recipe's validate()/build_context() accept a WebsocketListenerIR (NOT a
HandlerIR). An isinstance guard rejects HandlerIR up front so the recipe cannot
be mis-dispatched via the per-handler loop — honoring the Recipe ABC's typed
contract without needing a separate ABC.
"""

from __future__ import annotations

from bmgen.ir.model import HandlerIR, WebsocketListenerIR
from bmgen.recipes.base import Recipe, RecipeContext


class WebsocketBridgeRecipe(Recipe):
    """Recipe for bridging an external websocket stream onto a CAN restbus.

    Reads JSON messages from a websocket URL, maps each payload key to a restbus
    signal, and publishes via restbus.update_signals. Reconnects with a warning
    on error. Runs as a background asyncio task for the model's lifetime.
    """

    @property
    def name(self) -> str:
        return "WebsocketBridge"

    @property
    def description(self) -> str:
        return (
            "Bridge an external websocket stream onto a CAN restbus: read JSON "
            "messages from a ws:// URL, map each payload key to a restbus signal, "
            "and publish. Reconnects with a warning on error. Model-level "
            "background task (not a CAN-frame handler)."
        )

    @property
    def template_name(self) -> str:
        return "handler_websocket.py.j2"

    def validate(self, listener_ir: WebsocketListenerIR | HandlerIR) -> list[str]:
        """Validate that a WebsocketListenerIR matches this recipe's requirements.

        Returns a list of error messages. Empty list means valid.
        Rejects HandlerIR up front (LSP guard) so this recipe cannot be
        mis-dispatched via the per-handler loop.
        """
        if not isinstance(listener_ir, WebsocketListenerIR):
            return [
                f"WebsocketBridge expects a WebsocketListenerIR, got {type(listener_ir).__name__}. "
                f"It is a model-level recipe, not a per-handler recipe."
            ]

        errors = []
        # Structural checks. Namespace existence / restbus are already enforced
        # by Invariant 12 in validators.py; these are a defense-in-depth mirror
        # so the recipe is safe to call directly (e.g. from context_builder).
        if not listener_ir.url or not (listener_ir.url.startswith("ws://") or listener_ir.url.startswith("wss://")):
            errors.append(f"WebsocketBridge requires a ws:// or wss:// url, got {listener_ir.url!r}")
        if not listener_ir.output_namespace:
            errors.append("WebsocketBridge requires an output_namespace")
        if not listener_ir.signal_map:
            errors.append("WebsocketBridge requires a non-empty signal_map (ws_key → signal)")
        if not listener_ir.cleanup:
            errors.append("WebsocketBridge requires cleanup=True (background task must be cancellable)")
        return errors

    def build_context(self, listener_ir: WebsocketListenerIR | HandlerIR) -> RecipeContext:
        """Build a template context dict from a validated WebsocketListenerIR.

        The output_namespace_var is NOT resolved here — the listener IR does not
        carry the namespace's python_var_name. The context_builder resolves it
        via its ns_var_lookup after calling this, mirroring how per-handler
        output_namespace_var is filled in _merge_recipe_context.
        """
        if not isinstance(listener_ir, WebsocketListenerIR):
            raise TypeError(
                f"WebsocketBridge.build_context expects a WebsocketListenerIR, "
                f"got {type(listener_ir).__name__}"
            )

        return RecipeContext(
            handler_name=listener_ir.name,
            pattern=self.name,
            template_name=self.template_name,
            context={
                "ws_name": listener_ir.name,
                "ws_url": listener_ir.url,
                "ws_output_namespace": listener_ir.output_namespace,
                "ws_output_namespace_var": "",  # filled by context_builder via ns_var_lookup
                "ws_signal_map": list(listener_ir.signal_map),
                "ws_reconnect_delay": listener_ir.reconnect_delay_sec,
                # Derived method names — keep them stable + name-safe.
                "ws_task_var_name": f"_ws_task_{_safe_var(listener_ir.name)}",
                "ws_start_name": f"_start_ws_{_safe_var(listener_ir.name)}",
                "ws_stop_name": f"_stop_ws_{_safe_var(listener_ir.name)}",
                "ws_handler_name": f"_ws_loop_{_safe_var(listener_ir.name)}",
            },
        )

    def required_fields(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "template": self.template_name,
            "required_input_count": 0,  # no CAN input — external websocket
            "required_output_count": "≥1",
            "requires_state": False,
            "requires_periodic": False,
            "requires_websocket": True,
        }


def _safe_var(name: str) -> str:
    """Convert a listener name to a Python-identifier-safe snake_case suffix."""
    result = []
    for ch in name:
        if ch.isalnum():
            result.append(ch.lower())
        elif ch in ("-", " ", "."):
            result.append("_")
        else:
            result.append("_")
    s = "".join(result)
    # Collapse runs of underscores and strip leading/trailing ones.
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_") or "listener"
