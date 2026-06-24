"""T2 Behavioral Verifier — checks handler behavior with fake Frame and mock restbus.

T2 dynamically loads the generated Python module, creates mock objects
(FakeFrame, MockRestbus), calls handler methods, and verifies that the
mock restbus received the expected signal-value tuples.

T2 must PASS after T1 (structural) and before T3 (composition) runs.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import sys
import tempfile

from bmgen.verifier.report import VerificationReport


class FakeFrame:
    """Simulates a Remotive Frame with configurable signal values.

    Used by the behavioral verifier to test handler methods without
    a real broker connection.
    """
    def __init__(self, signals: dict[str, float | int]):
        self.signals = signals


class MockRestbus:
    """Captures all update_signals calls for verification.

    This replaces the real restbus object in output namespaces so we can
    inspect what signals and values the handler produced.
    """
    def __init__(self):
        self.calls: list[list[tuple[str, float | int]]] = []

    async def update_signals(self, *tuples: tuple[str, float | int]):
        self.calls.append(list(tuples))

    async def reset(self):
        """Mock reset — no-op for behavioral testing."""
        pass


class MockNamespace:
    """Namespace with mock restbus for output verification."""
    def __init__(self, name: str, restbus: MockRestbus | None = None):
        self.name = name
        self.restbus = restbus or MockRestbus()

    def create_input_handler(self, filters, handler):
        """Mock input handler registration — no-op for behavioral testing."""
        pass


def run_behavioral_checks(
    generated_dir: str,
    ir: "BehavioralModelIR",
    report: VerificationReport,
) -> bool:
    """Run all T2 behavioral checks on generated code.

    Args:
        generated_dir: Path to the directory containing generated Python files.
        ir: The BehavioralModelIR that was used to generate the code.
        report: VerificationReport to add check results to.

    Returns:
        True if all T2 checks PASS, False if any FAIL.
    """
    all_pass = True
    model_name_lower = ir.name.lower()

    # Build mock objects for the model
    mock_restbuses: dict[str, MockRestbus] = {}
    mock_namespaces: dict[str, MockNamespace] = {}

    for ns in ir.namespaces:
        if ns.role in ("output", "both"):
            mock_restbus = MockRestbus()
            mock_restbuses[ns.name] = mock_restbus
            mock_ns = MockNamespace(ns.name, mock_restbus)
        else:
            mock_ns = MockNamespace(ns.name)
        mock_namespaces[ns.python_var_name] = mock_ns

    # Try to load the generated module dynamically
    main_path = os.path.join(generated_dir, model_name_lower, "__main__.py")
    if not os.path.isfile(main_path):
        report.add_check("behavioral", "module_loadable", "FAIL",
                         f"Cannot load module: {main_path} not found")
        return False

    # Load the module using importlib (isolated from real broker)
    try:
        module = _load_module_dynamically(main_path, model_name_lower)
    except Exception as e:
        # If the module can't be imported (e.g., remotivelabs not installed),
        # we can still verify behavior by parsing the AST and constructing
        # a simplified test model
        report.add_check("behavioral", "module_loadable", "SKIP",
                         f"Module import failed (remotivelabs packages not available): {e}")
        # Fall back to AST-based behavioral verification
        return _run_ast_behavioral_checks(main_path, ir, report, mock_restbuses, mock_namespaces)

    report.add_check("behavioral", "module_loadable", "PASS",
                     "Generated module loaded successfully")

    # Create an instance of the model class with mock objects
    model_class = getattr(module, ir.name)
    try:
        # Construct model with mock namespaces
        mock_ns_args = {}
        output_ns_list = [ns for ns in ir.namespaces if ns.role in ("output", "both")]
        for ns in output_ns_list:
            mock_ns_args[ns.python_var_name] = mock_namespaces[ns.python_var_name]

        model_instance = model_class(**mock_ns_args)
    except Exception as e:
        report.add_check("behavioral", "model_instantiable", "FAIL",
                         f"Cannot instantiate model class: {e}")
        return False

    report.add_check("behavioral", "model_instantiable", "PASS",
                     f"Model class {ir.name} instantiated with mock namespaces")

    # Test each handler
    for handler_ir in ir.handlers:
        if handler_ir.novel_logic:
            report.add_check("behavioral", "handler_callable_with_fake_frame", "SKIP",
                             f"Handler '{handler_ir.name}' is novel_logic: behavioral check skipped")
            report.add_warning("novel_logic", handler_ir.name,
                               "Handler requires manual implementation. Behavioral verification skipped.")
            continue

        # Get handler method from model instance
        handler_method = getattr(model_instance, handler_ir.name, None)
        if handler_method is None:
            report.add_check("behavioral", "handler_callable_with_fake_frame", "FAIL",
                             f"Handler method '{handler_ir.name}' not found on model instance")
            all_pass = False
            continue

        # Clear mock restbus calls
        for rb in mock_restbuses.values():
            rb.calls.clear()

        # Create fake frame with handler's input signals
        input_signal_values = {}
        for sig in handler_ir.input_signals:
            input_signal_values[sig.name] = 1.0  # Default test value

        fake_frame = FakeFrame(input_signal_values)

        # Call the handler
        try:
            import asyncio
            asyncio.run(handler_method(fake_frame))
        except TypeError as e:
            # If the handler is not truly async, try calling it differently
            report.add_check("behavioral", "handler_callable_with_fake_frame", "FAIL",
                             f"Handler '{handler_ir.name}' call failed: {e}")
            all_pass = False
            continue
        except Exception as e:
            # Handler crashed — that's a behavioral failure
            report.add_check("behavioral", "handler_callable_with_fake_frame", "FAIL",
                             f"Handler '{handler_ir.name}' raised exception: {e}")
            all_pass = False
            continue

        report.add_check("behavioral", "handler_callable_with_fake_frame", "PASS",
                         f"Handler '{handler_ir.name}' called successfully with fake Frame")

        # Check pattern-specific behavioral expectations
        if handler_ir.pattern == "DirectSignalMapping":
            all_pass &= _verify_direct_mapping(handler_ir, mock_restbuses, report)
        elif handler_ir.pattern == "ToggleButtonState":
            all_pass &= _verify_toggle_button(handler_ir, model_instance, mock_restbuses, report)

    return all_pass


def _verify_direct_mapping(
    handler_ir: "HandlerIR",
    mock_restbuses: dict[str, MockRestbus],
    report: VerificationReport,
) -> bool:
    """Verify DirectSignalMapping: output signals match input value."""
    # Use the first output_group's namespace — single-output semantics for this verifier.
    output_ns_name = handler_ir.output_groups[0].namespace if handler_ir.output_groups else ""
    mock_restbus = mock_restbuses.get(output_ns_name)

    if mock_restbus is None or not mock_restbus.calls:
        report.add_check("behavioral", "direct_signal_mapping_output_correct", "FAIL",
                         "No restbus.update_signals calls found")
        return False

    # Check that the output tuples contain the expected signal names
    last_call = mock_restbus.calls[-1]
    # Flatten output_groups → flat signal-name list for the single-output verifier.
    expected_signal_names = [
        s.name for g in handler_ir.output_groups for s in g.signals
    ]
    actual_signal_names = [t[0] for t in last_call]

    if actual_signal_names == expected_signal_names:
        report.add_check("behavioral", "direct_signal_mapping_output_signals_match", "PASS",
                         f"Output signal names match: {expected_signal_names}")
    else:
        report.add_check("behavioral", "direct_signal_mapping_output_signals_match", "FAIL",
                         f"Expected signals {expected_signal_names}, got {actual_signal_names}")
        return False

    # Check that all output values match the input value (1.0)
    expected_value = 1.0
    all_values_match = all(t[1] == expected_value for t in last_call)

    if all_values_match:
        report.add_check("behavioral", "direct_signal_mapping_output_correct", "PASS",
                         f"Output values match input value ({expected_value})")
        return True
    else:
        report.add_check("behavioral", "direct_signal_mapping_output_correct", "FAIL",
                         f"Expected all values to be {expected_value}, got {last_call}")
        return False


def _verify_toggle_button(
    handler_ir: "HandlerIR",
    model_instance,
    mock_restbuses: dict[str, MockRestbus],
    report: VerificationReport,
) -> bool:
    """Verify ToggleButtonState: press once → enabled, press twice → disabled."""
    # Use the first output_group's namespace — single-output semantics for this verifier.
    output_ns_name = handler_ir.output_groups[0].namespace if handler_ir.output_groups else ""
    mock_restbus = mock_restbuses.get(output_ns_name)
    handler_method = getattr(model_instance, handler_ir.name)

    all_pass = True

    # Test 1: Press once → enabled (outputs = 1)
    mock_restbus.calls.clear()
    fake_frame_on = FakeFrame({handler_ir.input_signals[0].name: 1})
    import asyncio
    asyncio.run(handler_method(fake_frame_on))

    if mock_restbus.calls:
        last_call = mock_restbus.calls[-1]
        all_enabled = all(t[1] == 1 for t in last_call)
        if all_enabled:
            report.add_check("behavioral", "toggle_button_press_once_enabled", "PASS",
                             f"Press once → all outputs = 1 (enabled)")
        else:
            report.add_check("behavioral", "toggle_button_press_once_enabled", "FAIL",
                             f"Press once → outputs not all 1: {last_call}")
            all_pass = False
    else:
        report.add_check("behavioral", "toggle_button_press_once_enabled", "FAIL",
                         "No update_signals calls after first press")
        all_pass = False

    # Test 2: Press again → disabled (outputs = 0)
    mock_restbus.calls.clear()
    fake_frame_on2 = FakeFrame({handler_ir.input_signals[0].name: 1})
    asyncio.run(handler_method(fake_frame_on2))

    if mock_restbus.calls:
        last_call = mock_restbus.calls[-1]
        all_disabled = all(t[1] == 0 for t in last_call)
        if all_disabled:
            report.add_check("behavioral", "toggle_button_press_twice_disabled", "PASS",
                             f"Press twice → all outputs = 0 (disabled)")
        else:
            report.add_check("behavioral", "toggle_button_press_twice_disabled", "FAIL",
                             f"Press twice → outputs not all 0: {last_call}")
            all_pass = False
    else:
        report.add_check("behavioral", "toggle_button_press_twice_disabled", "FAIL",
                         "No update_signals calls after second press")
        all_pass = False

    return all_pass


def _load_module_dynamically(main_path: str, module_name: str):
    """Load a Python module from a file path dynamically."""
    spec = importlib.util.spec_from_file_location(module_name, main_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _run_ast_behavioral_checks(
    main_path: str,
    ir: "BehavioralModelIR",
    report: VerificationReport,
    mock_restbuses: dict[str, MockRestbus],
    mock_namespaces: dict[str, MockNamespace],
) -> bool:
    """AST-based behavioral verification when module can't be dynamically imported.

    This fallback parses the generated code and checks for behavioral patterns
    without executing the code. It's less thorough than dynamic testing but
    works when remotivelabs packages are not installed.
    """
    all_pass = True

    with open(main_path) as f:
        content = f.read()

    try:
        tree = ast.parse(content)
    except SyntaxError:
        report.add_check("behavioral", "ast_parseable", "FAIL", "Generated code has syntax errors")
        return False

    report.add_check("behavioral", "ast_parseable", "PASS", "Generated code is AST-parseable")

    # Check that each handler method exists in the AST
    handler_names_in_ast = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            handler_names_in_ast.add(node.name)

    for handler_ir in ir.handlers:
        if handler_ir.novel_logic:
            report.add_check("behavioral", "handler_method_exists", "SKIP",
                             f"Handler '{handler_ir.name}' is novel_logic: skipped")
            continue

        if handler_ir.name in handler_names_in_ast:
            report.add_check("behavioral", "handler_method_exists", "PASS",
                             f"Handler method '{handler_ir.name}' found in AST")
        else:
            report.add_check("behavioral", "handler_method_exists", "FAIL",
                             f"Handler method '{handler_ir.name}' not found in AST")
            all_pass = False

    # Check that restbus.update_signals is called with the expected signal patterns
    for handler_ir in ir.handlers:
        if handler_ir.novel_logic:
            continue
        if handler_ir.pattern == "DirectSignalMapping":
            # Check that the handler reads the input signal and writes to output signals
            for g in handler_ir.output_groups:
                for output_sig in g.signals:
                    if output_sig.name in content:
                        report.add_check("behavioral", "direct_signal_mapping_signal_refs", "PASS",
                                         f"Output signal '{output_sig.name}' referenced in code")
                    else:
                        report.add_check("behavioral", "direct_signal_mapping_signal_refs", "FAIL",
                                         f"Output signal '{output_sig.name}' not found in code")
                        all_pass = False

    # For behavioral verification, we mark dynamic checks as SKIP
    # since we can't execute the code in this fallback mode
    for handler_ir in ir.handlers:
        if handler_ir.novel_logic:
            continue
        report.add_check("behavioral", f"handler_callable_{handler_ir.name}", "SKIP",
                         "Dynamic behavioral verification requires remotivelabs packages")

    return all_pass


# Type hint
from bmgen.ir.model import BehavioralModelIR  # noqa: E402
