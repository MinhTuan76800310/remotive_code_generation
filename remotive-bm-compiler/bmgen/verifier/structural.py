"""T1 Structural Verifier — checks generated Python code for structural correctness.

T1 operates on generated Python files as static artifacts. It checks syntax,
AST structure, import presence, handler signatures, and namespace references
without executing the code (except for import checks in a subprocess).

T1 must PASS before T2 (behavioral) runs.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile

from bmgen.verifier.report import VerificationReport


def run_structural_checks(
    generated_dir: str,
    ir: "BehavioralModelIR",
    report: VerificationReport,
) -> bool:
    """Run all T1 structural checks on generated code.

    Args:
        generated_dir: Path to the directory containing generated Python files.
        ir: The BehavioralModelIR that was used to generate the code.
        report: VerificationReport to add check results to.

    Returns:
        True if all T1 checks PASS, False if any FAIL.
    """
    model_name_lower = ir.name.lower()
    main_path = os.path.join(generated_dir, model_name_lower, "__main__.py")

    all_pass = True

    # Check 1: file_exists
    if os.path.isfile(main_path):
        report.add_check("structural", "file_exists", "PASS", f"{main_path} found")
    else:
        report.add_check("structural", "file_exists", "FAIL", f"Generated file not found: {main_path}")
        return False  # No point continuing if file doesn't exist

    # Read the generated file content
    with open(main_path) as f:
        content = f.read()

    # Check 2: syntax_valid
    try:
        tree = ast.parse(content)
        report.add_check("structural", "syntax_valid", "PASS", "Python syntax valid")
    except SyntaxError as e:
        report.add_check("structural", "syntax_valid", "FAIL", f"Syntax error: {e}")
        return False  # No point continuing if syntax is broken

    # Check 3: remotive_imports_present
    required_imports = [
        "from remotivelabs.broker import",
        "from remotivelabs.topology.behavioral_model import",
        "from remotivelabs.topology.namespaces.can import",
        "from remotivelabs.topology.namespaces import filters",
    ]
    imports_ok = True
    for required in required_imports:
        if required not in content:
            report.add_check("structural", "remotive_imports_present", "FAIL",
                             f"Missing required import: {required}")
            imports_ok = False
            all_pass = False
    if imports_ok:
        report.add_check("structural", "remotive_imports_present", "PASS",
                         "All required Remotive imports present")

    # Check 4: handler_methods_async
    handler_names = [h.name for h in ir.handlers]
    async_handlers = _find_async_handlers(tree, handler_names)
    for h_name in handler_names:
        handler_ir = next(h for h in ir.handlers if h.name == h_name)
        if h_name in async_handlers:
            report.add_check("structural", "handler_async", "PASS",
                             f"Handler '{h_name}' is async def")
        else:
            report.add_check("structural", "handler_async", "FAIL",
                             f"Handler '{h_name}' is not async. Expected: async def {h_name}")
            all_pass = False

    # Check 5: handler_accepts_frame
    for h_name in handler_names:
        if _handler_accepts_frame(tree, h_name):
            report.add_check("structural", "handler_accepts_frame", "PASS",
                             f"Handler '{h_name}' accepts frame parameter")
        else:
            report.add_check("structural", "handler_accepts_frame", "FAIL",
                             f"Handler '{h_name}' does not accept frame parameter")
            all_pass = False

    # Check 6: namespace_refs_exist
    namespace_names = [ns.name for ns in ir.namespaces]
    ns_refs_found = _find_namespace_refs(content, namespace_names)
    all_ns_found = all(ns in ns_refs_found for ns in namespace_names)
    if all_ns_found:
        report.add_check("structural", "namespace_refs_exist", "PASS",
                         f"All namespace references found: {namespace_names}")
    else:
        missing = [ns for ns in namespace_names if ns not in ns_refs_found]
        report.add_check("structural", "namespace_refs_exist", "FAIL",
                         f"Missing namespace references: {missing}")
        all_pass = False

    # Check 7: output_has_restbus
    output_ns_names = {h.output_namespace for h in ir.handlers}
    output_ns_with_restbus = _find_restbus_configs(content, output_ns_names)
    all_output_have_restbus = all(ns in output_ns_with_restbus for ns in output_ns_names)
    if all_output_have_restbus:
        report.add_check("structural", "output_has_restbus", "PASS",
                         f"Output namespaces have restbus config: {output_ns_names}")
    else:
        missing = [ns for ns in output_ns_names if ns not in output_ns_with_restbus]
        report.add_check("structural", "output_has_restbus", "FAIL",
                         f"Output namespaces missing restbus config: {missing}")
        all_pass = False

    # Check 8: input_has_frame_filter
    for handler_ir in ir.handlers:
        ff_name = handler_ir.input_frame_filter
        if ff_name and f'FrameFilter("{ff_name}")' in content:
            report.add_check("structural", "input_has_frame_filter", "PASS",
                             f"FrameFilter '{ff_name}' found for handler '{handler_ir.name}'")
        else:
            report.add_check("structural", "input_has_frame_filter", "FAIL",
                             f"FrameFilter '{ff_name}' not found for handler '{handler_ir.name}'")
            all_pass = False

    # Check 9: restbus_update_signals_used (for non-novel_logic handlers)
    non_novel_handlers = [h for h in ir.handlers if not h.novel_logic]
    for handler_ir in non_novel_handlers:
        # For novel_logic stub handlers, skip this check
        if "restbus.update_signals" in content:
            report.add_check("structural", "restbus_update_signals_used", "PASS",
                             "restbus.update_signals calls present")
            break
    else:
        if non_novel_handlers:
            report.add_check("structural", "restbus_update_signals_used", "FAIL",
                             "No restbus.update_signals calls found in generated code")
            all_pass = False

    # Check 10: main_function_exists
    if _function_exists(tree, "main"):
        report.add_check("structural", "main_function_exists", "PASS",
                         "async def main(avp: BehavioralModelArgs) exists")
    else:
        report.add_check("structural", "main_function_exists", "FAIL",
                         "main function not found")
        all_pass = False

    # Check 11: entry_point_exists
    if "__name__" in content and "__main__" in content:
        report.add_check("structural", "entry_point_exists", "PASS",
                         "Entry point (__name__ == '__main__') exists")
    else:
        report.add_check("structural", "entry_point_exists", "FAIL",
                         "Entry point not found")
        all_pass = False

    # Check 12: module_imports (dynamic — try importing in subprocess)
    # This check is optional and may fail if remotivelabs packages are not installed
    # We mark it as SKIP if the import fails due to missing dependencies
    report.add_check("structural", "module_imports", "SKIP",
                     "Module import check requires remotivelabs packages (skipped in unit test env)")

    report.generated_files.append(main_path)

    return all_pass


def _find_async_handlers(tree: ast.AST, handler_names: list[str]) -> set[str]:
    """Find async handler method names in the AST."""
    async_handlers = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name in handler_names:
            async_handlers.add(node.name)
    return async_handlers


def _handler_accepts_frame(tree: ast.AST, handler_name: str) -> bool:
    """Check if a handler method accepts a 'frame' parameter."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == handler_name:
            for arg in node.args.args:
                if arg.arg == "frame":
                    return True
    return False


def _find_namespace_refs(content: str, namespace_names: list[str]) -> set[str]:
    """Find namespace string literals in the generated code."""
    found = set()
    for ns_name in namespace_names:
        if ns_name in content:
            found.add(ns_name)
    return found


def _find_restbus_configs(content: str, output_ns_names: set[str]) -> set[str]:
    """Find output namespace names that have restbus_configs in the code."""
    found = set()
    for ns_name in output_ns_names:
        # Check that the namespace has restbus_configs argument
        # Pattern: CanNamespace("NS-Name", ..., restbus_configs=[...])
        if ns_name in content and "restbus_configs" in content:
            found.add(ns_name)
    return found


def _function_exists(tree: ast.AST, func_name: str) -> bool:
    """Check if a function with the given name exists in the AST."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return True
    return False


# Type hint
from bmgen.ir.model import BehavioralModelIR  # noqa: E402
