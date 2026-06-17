"""Python code generator — orchestrates Jinja2 template rendering.

The generator takes a template context dict (from context_builder) and renders
the main.py.j2 template to produce a complete Remotive Behavioral Model Python
file. It also generates supporting files (__init__.py, log.py).

Handler templates are rendered separately and passed as pre-rendered strings
into the main template. This avoids Jinja2 scoping issues with {% include %}
and makes the template context more explicit.

The generator is deterministic: the same context always produces the same output.
No randomness, no LLM, no external services.
"""

from __future__ import annotations

from pathlib import Path

import jinja2


def generate(
    context: dict,
    output_dir: str,
) -> list[str]:
    """Generate behavioral model Python files from template context.

    Args:
        context: Unified template context from context_builder.
        output_dir: Directory to write generated files to.

    Returns:
        List of generated file paths (relative to output_dir).
    """
    model_name_lower = context["model_name_lower"]
    model_dir = Path(output_dir) / model_name_lower
    model_dir.mkdir(parents=True, exist_ok=True)

    # Set up Jinja2 environment with template directory
    template_dir = Path(__file__).parent / "templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Pre-render each handler template separately
    handler_bodies = []
    for handler in context["handlers"]:
        if handler["novel_logic"]:
            # Render novel_logic handler inline
            body = _render_novel_logic_handler(handler)
        elif handler["template_name"]:
            # Render handler template with handler-specific context
            template = env.get_template(handler["template_name"])
            # Flatten handler context for template rendering
            handler_flat = {}
            # Add all top-level handler fields
            handler_flat.update(handler)
            # Also add key fields at top level for template convenience
            handler_flat["handler_name"] = handler.get("handler_name", handler.get("name", ""))
            handler_flat["output_namespace_var"] = handler.get("output_namespace_var", "")
            handler_flat["input_signal_var"] = handler.get("input_signal_var", "")
            handler_flat["input_signal_ref"] = handler.get("input_signal_ref", "")
            handler_flat["output_tuples"] = handler.get("output_tuples", [])
            body = template.render(**handler_flat)
        else:
            body = ""
        handler_bodies.append({
            "name": handler.get("name", handler.get("handler_name", "")),
            "body": _indent_body(body.strip(), indent=4),
        })

    # Pre-render reset handler if needed
    reset_handler_body = ""
    if context.get("has_reset_handler") and context.get("reset_states"):
        reset_template = env.get_template("handler_reset.py.j2")
        reset_ctx = {
            "reset_states": context["reset_states"],
            "reset_namespace_vars": context.get("reset_namespace_vars", []),
        }
        reset_handler_body = _indent_body(reset_template.render(**reset_ctx).strip(), indent=4)

    # Build the full main.py context with pre-rendered handler bodies
    main_context = dict(context)
    main_context["handler_bodies"] = handler_bodies
    main_context["reset_handler_body"] = reset_handler_body

    # Render main.py
    main_template = env.get_template("main.py.j2")
    main_content = main_template.render(**main_context)
    main_path = model_dir / "__main__.py"
    main_path.write_text(main_content)

    # Generate __init__.py
    init_content = ""
    init_path = model_dir / "__init__.py"
    init_path.write_text(init_content)

    # Generate log.py (simple logging configuration)
    log_content = _generate_log_py()
    log_path = model_dir / "log.py"
    log_path.write_text(log_content)

    # Return relative paths
    generated_files = [
        str(main_path.relative_to(output_dir)),
        str(init_path.relative_to(output_dir)),
        str(log_path.relative_to(output_dir)),
    ]

    return generated_files


def _indent_body(body: str, indent: int = 4) -> str:
    """Add indentation to a multi-line body string.

    Each line of the body gets `indent` spaces prepended.
    Empty lines are preserved but not indented.
    """
    prefix = " " * indent
    lines = body.split("\n")
    indented_lines = []
    for line in lines:
        if line.strip():  # Non-empty line: add indentation
            indented_lines.append(prefix + line)
        else:  # Empty line: keep empty
            indented_lines.append("")
    return "\n".join(indented_lines)


def _render_novel_logic_handler(handler: dict) -> str:
    """Render a novel_logic stub handler."""
    name = handler.get("name", handler.get("handler_name", ""))
    pattern = handler.get("pattern", "Unknown")
    input_signals = handler.get("input_signals", [])
    output_signals = handler.get("output_signals", [])

    lines = [
        f"    async def {name}(self, frame: Frame) -> None:",
        "        # novel_logic: implement manually",
        f"        # pattern: {pattern}",
    ]
    if input_signals:
        lines.append(f"        # input: {input_signals[0]['name']} from {handler.get('input_namespace', '')}")
    if output_signals:
        output_names = [s['name'] for s in output_signals]
        lines.append(f"        # output: {', '.join(output_names)} to {handler.get('output_namespace', '')}")
    lines.append("        pass")

    return "\n".join(lines)


def _generate_log_py() -> str:
    """Generate the log.py module with structlog configuration."""
    return '''"""Logging configuration for the behavioral model."""

import logging

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog for the behavioral model."""
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger_from_min_level(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
'''
