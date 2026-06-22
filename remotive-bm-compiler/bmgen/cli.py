"""CLI entry point for bmgen — the Remotive Behavioral Model Compiler.

Provides four subcommands:
- parse: Parse a YAML spec and print the validated IR
- generate: Parse YAML + compile + generate Python files
- verify: Run 3-layer verification on generated code
- recipes: List available recipe patterns
"""

from __future__ import annotations

import argparse
import json
import sys

import structlog

from bmgen.ir.builder import build_ir, BuilderError
from bmgen.ir.model import BehavioralModelIR
from bmgen.ir.parser import parse_yaml_file
from bmgen.compiler.context_builder import build_template_context
from bmgen.compiler.python_generator import generate
from bmgen.recipes.registry import create_default_registry
from bmgen.verifier.runner import run_verification, format_report_json

logger = structlog.get_logger(__name__)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="bmgen",
        description="Remotive Behavioral Model Compiler — deterministic code generation from YAML specs",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # parse subcommand
    parse_cmd = subparsers.add_parser("parse", help="Parse a YAML spec and print the validated IR")
    parse_cmd.add_argument("yaml_file", help="Path to the YAML spec file")
    parse_cmd.add_argument("--json", action="store_true", help="Output as JSON")

    # generate subcommand
    gen_cmd = subparsers.add_parser("generate", help="Generate Python behavioral model from YAML spec")
    gen_cmd.add_argument("yaml_file", help="Path to the YAML spec file")
    gen_cmd.add_argument("--out", required=True, help="Output directory for generated files")

    # verify subcommand
    verify_cmd = subparsers.add_parser("verify", help="Verify generated Python behavioral model")
    verify_cmd.add_argument("generated_dir", help="Path to the directory containing generated files")
    verify_cmd.add_argument("--spec", help="Path to the original YAML spec (for IR context)")
    verify_cmd.add_argument("--json", action="store_true", help="Output verification report as JSON")

    # recipes subcommand
    recipes_cmd = subparsers.add_parser("recipes", help="List available recipe patterns")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "parse":
            _cmd_parse(args)
        elif args.command == "generate":
            _cmd_generate(args)
        elif args.command == "verify":
            _cmd_verify(args)
        elif args.command == "recipes":
            _cmd_recipes()
    except BuilderError as e:
        logger.error("IR validation failed", violations=e.violations)
        print(f"Error: IR validation failed\n{e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.exception("Command failed", command=args.command, error=e)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_parse(args):
    """Parse a YAML spec and print the validated IR."""
    spec = parse_yaml_file(args.yaml_file)
    ir = build_ir(spec)

    if args.json:
        ir_dict = _ir_to_dict(ir)
        print(json.dumps(ir_dict, indent=2))
    else:
        print(f"Model: {ir.name} (ECU: {ir.ecu_name})")
        print(f"Namespaces: {len(ir.namespaces)}")
        for ns in ir.namespaces:
            restbus_info = f" (restbus: sender_filter={ns.restbus.sender_filter})" if ns.restbus else ""
            print(f"  - {ns.name} ({ns.type}, role={ns.role}, var={ns.python_var_name}){restbus_info}")
        print(f"Handlers: {len(ir.handlers)}")
        for h in ir.handlers:
            print(f"  - {h.name} (pattern={h.pattern}, novel_logic={h.novel_logic})")
            print(f"    Input: {h.input_namespace} / {h.input_frame_filter} / {h.input_signals[0].name if h.input_signals else 'none'}")
            print(f"    Output: {h.output_namespace} / {[s.name for s in h.output_signals]}")
            if h.state:
                print(f"    State: {h.state.name} ({h.state.type}, initial={h.state.initial})")
        print(f"Reset handler: {ir.reset_handler is not None}")
        print(f"Novel logic handlers: {ir.novel_logic_handlers}")
        print("Validation: PASS")


def _cmd_generate(args):
    """Generate Python behavioral model from YAML spec."""
    spec = parse_yaml_file(args.yaml_file)
    ir = build_ir(spec)

    registry = create_default_registry()

    # Validate each handler against its recipe
    for handler in ir.handlers:
        if handler.novel_logic:
            continue
        recipe = registry.get(handler.pattern)
        if recipe is None:
            raise ValueError(f"Unknown pattern '{handler.pattern}' for handler '{handler.name}'")
        errors = recipe.validate(handler)
        if errors:
            raise ValueError(f"Handler '{handler.name}' failed recipe validation: {errors}")

    # Build template context
    context = build_template_context(ir, registry)

    # Generate code
    generated_files = generate(context, args.out)

    logger.info("Code generation complete", files=generated_files)
    print(f"Generated {len(generated_files)} files in {args.out}:")
    for f in generated_files:
        print(f"  - {f}")


def _cmd_verify(args):
    """Verify generated Python behavioral model."""
    # Load the IR from the spec if provided
    if args.spec:
        spec = parse_yaml_file(args.spec)
        ir = build_ir(spec)
    else:
        # Try to reconstruct IR from generated directory
        # This is a fallback — ideally the spec is always provided
        logger.warning("No spec file provided, using minimal IR for verification")
        ir = _infer_minimal_ir(args.generated_dir)

    report = run_verification(args.generated_dir, ir)

    if args.json:
        print(format_report_json(report))
    else:
        print(f"Verification result: {report.status}")
        print(f"Checks: {len(report.checks)}")
        for check in report.checks:
            status_symbol = "✓" if check.status == "PASS" else "✗" if check.status == "FAIL" else "○"
            print(f"  {status_symbol} [{check.layer}] {check.name}: {check.status}")
            if check.message:
                print(f"    {check.message}")
        if report.warnings:
            print("Warnings:")
            for w in report.warnings:
                print(f"  ⚠ [{w['type']}] {w['handler']}: {w['message']}")
        if report.errors:
            print("Errors:")
            for e in report.errors:
                print(f"  ✗ [{e['layer']}] {e['check']}: {e['message']}")

    if report.status == "FAIL":
        sys.exit(1)


def _cmd_recipes():
    """List available recipe patterns."""
    registry = create_default_registry()
    recipes = registry.list_all()

    print("Available recipes:")
    for recipe in recipes:
        fields = recipe.required_fields()
        print(f"  {fields['name']}: {fields['description']}")
        print(f"    Template: {fields['template']}")
        print(f"    Input: {fields.get('required_input_count', '?')} signal(s)")
        print(f"    Output: {fields.get('required_output_count', '?')} signal(s)")
        print(f"    Requires state: {fields.get('requires_state', '?')}")
        print(f"    Requires periodic: {fields.get('requires_periodic', '?')}")
        # Optional recipe-specific fields (e.g. ThresholdMapping's operator/true_when).
        if "requires_threshold" in fields:
            print(f"    Requires threshold: {fields['requires_threshold']}")
        if "optional_operator" in fields:
            print(f"    Optional operator: {fields['optional_operator']}")
            print(f"    Optional true_when: {fields.get('optional_true_when', [])}")
            if fields.get("operator_must_be_yaml_quoted"):
                print("    ⚠ operator MUST be YAML-quoted (operator: \">=\") — "
                      "unquoted '>' is a block-scalar indicator and fails at parse time.")
        print()


def _ir_to_dict(ir: BehavioralModelIR) -> dict:
    """Convert IR to a JSON-compatible dict for output."""
    result = {
        "model": {"name": ir.name, "ecu_name": ir.ecu_name},
        "namespaces": [],
        "handlers": [],
        "novel_logic_handlers": ir.novel_logic_handlers,
    }
    for ns in ir.namespaces:
        ns_dict = {
            "name": ns.name,
            "type": ns.type,
            "role": ns.role,
            "python_var_name": ns.python_var_name,
        }
        if ns.restbus:
            ns_dict["restbus"] = {"sender_filter": ns.restbus.sender_filter}
        result["namespaces"].append(ns_dict)

    for h in ir.handlers:
        h_dict = {
            "name": h.name,
            "pattern": h.pattern,
            "novel_logic": h.novel_logic,
            "input_namespace": h.input_namespace,
            "input_frame_filter": h.input_frame_filter,
            "input_signals": [{"name": s.name, "python_var_name": s.python_var_name} for s in h.input_signals],
            "output_namespace": h.output_namespace,
            "output_signals": [{"name": s.name, "value_expr": s.value_expr} for s in h.output_signals],
        }
        if h.state:
            h_dict["state"] = {
                "name": h.state.name,
                "type": h.state.type,
                "initial": h.state.initial,
                "reset_value": h.state.reset_value,
                "owner": h.state.owner,
            }
        result["handlers"].append(h_dict)

    return result


def _infer_minimal_ir(generated_dir: str) -> BehavioralModelIR:
    """Infer a minimal IR from the generated directory structure.

    This is a fallback for verification when no YAML spec is provided.
    It creates a minimal IR with just enough info for T1 structural checks.
    T2 and T3 checks may be limited without the full IR.
    """
    import os

    # Try to find the generated model directory
    subdirs = [d for d in os.listdir(generated_dir) if os.path.isdir(os.path.join(generated_dir, d))]
    if not subdirs:
        raise ValueError(f"No model directories found in {generated_dir}")

    model_dir_name = subdirs[0]
    model_name = model_dir_name.upper()  # e.g., "bcm" → "BCM"

    return BehavioralModelIR(
        name=model_name,
        ecu_name=model_name,
        namespaces=[],
        handlers=[],
    )


if __name__ == "__main__":
    main()
