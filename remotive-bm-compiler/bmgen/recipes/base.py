"""Abstract Recipe base class.

Every recipe must:
1. Have a unique name (e.g., "DirectSignalMapping")
2. Validate that a HandlerIR matches the recipe's requirements
3. Build a template context dict from the HandlerIR for Jinja2 rendering
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RecipeContext:
    """Template context produced by a recipe for Jinja2 rendering.

    This is a plain Python dict that the Jinja2 template consumes to produce
    handler method code. Each recipe populates this with the fields needed
    by its specific handler template.
    """
    handler_name: str
    pattern: str
    template_name: str  # Jinja2 template file (e.g., "handler_direct.py.j2")
    context: dict  # Recipe-specific template variables


class Recipe(ABC):
    """Abstract base class for behavioral model recipes.

    A recipe encapsulates a known ECU behavior pattern. It validates that
    a handler IR matches the pattern's structural requirements and produces
    a template context dict for deterministic code generation.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique recipe name (e.g., 'DirectSignalMapping')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Short human-readable description of the pattern."""
        ...

    @property
    @abstractmethod
    def template_name(self) -> str:
        """Jinja2 template file for this recipe's handler method."""
        ...

    @abstractmethod
    def validate(self, handler_ir: "HandlerIR") -> list[str]:
        """Validate that a HandlerIR matches this recipe's requirements.

        Returns a list of error messages. Empty list means valid.
        """
        ...

    @abstractmethod
    def build_context(self, handler_ir: "HandlerIR") -> RecipeContext:
        """Build a template context dict from a validated HandlerIR.

        Args:
            handler_ir: A HandlerIR that has already passed validate().

        Returns:
            RecipeContext with template name and context dict.
        """
        ...

    def required_fields(self) -> dict:
        """Return a dict describing the required IR fields for this recipe.

        Used by `bmgen recipes` to display recipe requirements.
        """
        return {
            "name": self.name,
            "description": self.description,
            "template": self.template_name,
        }


# Type hint for HandlerIR — avoids circular import
from bmgen.ir.model import HandlerIR  # noqa: E402
