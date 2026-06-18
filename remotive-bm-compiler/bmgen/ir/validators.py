"""IR invariant validation.

Checks all semantic rules that the IR dataclasses cannot enforce by themselves:
- Uniqueness constraints (namespace names, handler names, state ownership)
- Cross-reference validity (namespace references in handlers)
- Pattern consistency (output namespace must have restbus, state must have owner)
- Early failure on unknown patterns (unless novel_logic=True)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValidationViolation:
    """A single invariant violation found in the IR."""
    rule: str  # Invariant rule name (e.g., "namespace_names_unique")
    message: str  # Human-readable description
    severity: str = "error"  # "error" | "warning"


def validate(ir: "BehavioralModelIR") -> list[ValidationViolation]:
    """Validate all IR invariants. Returns a list of violations.

    If the list is empty, the IR is valid and can be passed to the compiler.
    If any severity="error" violation exists, the IR is invalid.
    """
    violations: list[ValidationViolation] = []

    violations.extend(_check_namespace_names_unique(ir))
    violations.extend(_check_handler_names_unique(ir))
    violations.extend(_check_handler_input_namespace_exists(ir))
    violations.extend(_check_handler_output_namespace_exists(ir))
    violations.extend(_check_output_namespace_has_restbus(ir))
    violations.extend(_check_state_single_owner(ir))
    violations.extend(_check_periodic_task_has_cleanup(ir))
    violations.extend(_check_resettable_state_has_reset_value(ir))
    violations.extend(_check_unknown_pattern_fails_early(ir))
    violations.extend(_check_novel_logic_handlers_listed(ir))

    return violations


def has_errors(violations: list[ValidationViolation]) -> bool:
    """Check if any violation has severity='error'."""
    return any(v.severity == "error" for v in violations)


def _check_namespace_names_unique(ir: "BehavioralModelIR") -> list[ValidationViolation]:
    """Invariant 1: Namespace names must be unique."""
    names = [ns.name for ns in ir.namespaces]
    duplicates = [name for name in names if names.count(name) > 1]
    if duplicates:
        return [
            ValidationViolation(
                rule="namespace_names_unique",
                message=f"Duplicate namespace names: {set(duplicates)}",
            )
        ]
    return []


def _check_handler_names_unique(ir: "BehavioralModelIR") -> list[ValidationViolation]:
    """Invariant 2: Handler names must be unique."""
    names = [h.name for h in ir.handlers]
    duplicates = [name for name in names if names.count(name) > 1]
    if duplicates:
        return [
            ValidationViolation(
                rule="handler_names_unique",
                message=f"Duplicate handler names: {set(duplicates)}",
            )
        ]
    return []


def _check_handler_input_namespace_exists(ir: "BehavioralModelIR") -> list[ValidationViolation]:
    """Invariant 3: Handler input_namespace must reference an existing namespace."""
    ns_names = {ns.name for ns in ir.namespaces}
    violations = []
    for handler in ir.handlers:
        if handler.input_namespace not in ns_names:
            violations.append(
                ValidationViolation(
                    rule="handler_input_namespace_exists",
                    message=f"Handler '{handler.name}' references non-existent input namespace '{handler.input_namespace}'",
                )
            )
    return violations


def _check_handler_output_namespace_exists(ir: "BehavioralModelIR") -> list[ValidationViolation]:
    """Invariant 4: Handler output_namespace must reference an existing namespace."""
    ns_names = {ns.name for ns in ir.namespaces}
    violations = []
    for handler in ir.handlers:
        if handler.output_namespace not in ns_names:
            violations.append(
                ValidationViolation(
                    rule="handler_output_namespace_exists",
                    message=f"Handler '{handler.name}' references non-existent output namespace '{handler.output_namespace}'",
                )
            )
    return violations


def _check_output_namespace_has_restbus(ir: "BehavioralModelIR") -> list[ValidationViolation]:
    """Invariant 5: Output namespace must have restbus config.

    In Remotive Behavioral Models, an output namespace (where restbus.update_signals
    is called) must have a RestbusConfig with a SenderFilter. This is required
    by the CanNamespace constructor for output namespaces.
    """
    violations = []
    output_ns_names = {h.output_namespace for h in ir.handlers}
    for ns in ir.namespaces:
        if ns.name in output_ns_names:
            if ns.role not in ("output", "both"):
                violations.append(
                    ValidationViolation(
                        rule="output_namespace_has_restbus",
                        message=f"Namespace '{ns.name}' is used as output but has role '{ns.role}' (must be 'output' or 'both')",
                    )
                )
            elif ns.restbus is None:
                violations.append(
                    ValidationViolation(
                        rule="output_namespace_has_restbus",
                        message=f"Output namespace '{ns.name}' has no restbus configuration (required for update_signals)",
                    )
                )
    return violations


def _check_state_single_owner(ir: "BehavioralModelIR") -> list[ValidationViolation]:
    """Invariant 6: Each state field must have exactly one owner."""
    violations = []
    owners_by_state: dict[str, list[str]] = {}
    for handler in ir.handlers:
        if handler.state is not None:
            state_name = handler.state.name
            owners_by_state.setdefault(state_name, []).append(handler.state.owner)

    for state_name, owners in owners_by_state.items():
        if len(owners) > 1:
            violations.append(
                ValidationViolation(
                    rule="state_single_owner",
                    message=f"State '{state_name}' has multiple owners: {owners}",
                )
            )
        # Also check that the owner matches a handler name
        if owners[0] not in {h.name for h in ir.handlers}:
            violations.append(
                ValidationViolation(
                    rule="state_single_owner",
                    message=f"State '{state_name}' owner '{owners[0]}' does not match any handler name",
                )
            )
    return violations


def _check_periodic_task_has_cleanup(ir: "BehavioralModelIR") -> list[ValidationViolation]:
    """Invariant 7: Periodic tasks must declare cleanup=True."""
    violations = []
    for handler in ir.handlers:
        if handler.periodic_task is not None:
            if not handler.periodic_task.cleanup:
                violations.append(
                    ValidationViolation(
                        rule="periodic_task_has_cleanup",
                        message=f"Handler '{handler.name}' has periodic task without cleanup=True (ticker must be cancelled on exit)",
                    )
                )
    return violations


def _check_resettable_state_has_reset_value(ir: "BehavioralModelIR") -> list[ValidationViolation]:
    """Invariant 8: States used in toggle/blink patterns must have reset_value."""
    violations = []
    for handler in ir.handlers:
        if handler.state is not None:
            if handler.pattern in ("ToggleButtonState", "PeriodicBlinkingOutput"):
                if handler.state.reset_value is None:
                    violations.append(
                        ValidationViolation(
                            rule="resettable_state_has_reset_value",
                            message=f"State '{handler.state.name}' in handler '{handler.name}' (pattern: {handler.pattern}) has no reset_value",
                        )
                    )
    return violations


def _check_unknown_pattern_fails_early(ir: "BehavioralModelIR") -> list[ValidationViolation]:
    """Invariant 9: Unknown pattern must fail early unless novel_logic=True.

    Patterns must be in the recipe registry. If a pattern is not recognized,
    the handler must be explicitly marked as novel_logic=True, which generates
    a stub handler instead.

    The known-pattern set is derived from the recipe registry itself, so
    registering a new recipe is sufficient — no edit to this validator is
    required. This keeps the registry the single source of truth.
    """
    # Import here to avoid a circular import (registry → recipes → ir.model).
    from bmgen.recipes.registry import create_default_registry

    registry = create_default_registry()
    known_patterns = registry.known_patterns()
    # DEBUG: print known patterns to stderr so CI logs capture them
    import sys
    sys.stderr.write(f"[DEBUG validator] known_patterns = {sorted(known_patterns)}\n")
    sys.stderr.flush()
    violations = []
    for handler in ir.handlers:
        if handler.pattern not in known_patterns and not handler.novel_logic:
            violations.append(
                ValidationViolation(
                    rule="unknown_pattern_fails_early",
                    message=f"Handler '{handler.name}' uses unknown pattern '{handler.pattern}'. "
                    f"Either add this pattern to the recipe registry or mark the handler as novel_logic=True.",
                )
            )
    return violations


def _check_novel_logic_handlers_listed(ir: "BehavioralModelIR") -> list[ValidationViolation]:
    """Invariant 10: novel_logic handlers must be listed in BehavioralModelIR.novel_logic_handlers."""
    violations = []
    actual_novel = {h.name for h in ir.handlers if h.novel_logic}
    declared_novel = set(ir.novel_logic_handlers)
    if actual_novel != declared_novel:
        missing = actual_novel - declared_novel
        extra = declared_novel - actual_novel
        msg_parts = []
        if missing:
            msg_parts.append(f"Handlers with novel_logic=True but not listed: {missing}")
        if extra:
            msg_parts.append(f"Handlers listed as novel_logic but not marked: {extra}")
        violations.append(
            ValidationViolation(
                rule="novel_logic_handlers_listed",
                message="; ".join(msg_parts),
            )
        )
    return violations


# Type hint for BehavioralModelIR — avoids circular import
from bmgen.ir.model import BehavioralModelIR  # noqa: E402
