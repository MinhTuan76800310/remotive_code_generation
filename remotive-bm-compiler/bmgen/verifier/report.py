"""Verification report — aggregates check results into JSON report."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CheckResult:
    """A single verification check result."""
    layer: str  # "structural" | "behavioral" | "composition"
    name: str  # Check name (e.g., "handler_async")
    status: str  # "PASS" | "FAIL" | "SKIP"
    message: str  # Human-readable result description


@dataclass
class VerificationReport:
    """Complete verification report with all check results.

    The report follows the JSON schema defined in VERIFIER_DESIGN.md.
    Overall status is PASS only if all checks have status PASS or SKIP.
    Any FAIL check makes the overall status FAIL.
    """
    status: str = "PASS"  # "PASS" | "FAIL"
    checks: list[CheckResult] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)

    def add_check(self, layer: str, name: str, status: str, message: str = "") -> None:
        """Add a check result to the report."""
        check = CheckResult(layer=layer, name=name, status=status, message=message)
        self.checks.append(check)

        if status == "FAIL":
            self.errors.append({
                "layer": layer,
                "check": name,
                "message": message,
            })
            self.status = "FAIL"

    def add_warning(self, warning_type: str, handler: str, message: str) -> None:
        """Add a warning to the report."""
        self.warnings.append({
            "type": warning_type,
            "handler": handler,
            "message": message,
        })

    def to_dict(self) -> dict[str, Any]:
        """Convert the report to a JSON-compatible dict."""
        return {
            "status": self.status,
            "checks": [
                {
                    "layer": c.layer,
                    "name": c.name,
                    "status": c.status,
                    "message": c.message,
                }
                for c in self.checks
            ],
            "generated_files": self.generated_files,
            "errors": self.errors,
            "warnings": self.warnings,
        }
