"""Recipe registry — flat lookup of known behavior patterns.

The registry is a simple Python dict mapping pattern names to Recipe instances.
This is NOT a graph database. It is a deterministic, flat lookup table.

To add a new recipe:
1. Create a Recipe subclass in bmgen/recipes/
2. Import it here
3. Register it with registry.register()
"""

from __future__ import annotations

from bmgen.recipes.base import Recipe
from bmgen.recipes.direct_signal_mapping import DirectSignalMappingRecipe
from bmgen.recipes.toggle_button_state import ToggleButtonStateRecipe
from bmgen.recipes.periodic_blinking_output import PeriodicBlinkingOutputRecipe


class RecipeRegistry:
    """Flat registry of known behavioral model recipes.

    Maps pattern names to Recipe instances for deterministic lookup.
    """

    def __init__(self):
        self._recipes: dict[str, Recipe] = {}

    def register(self, recipe: Recipe) -> None:
        """Register a recipe by its name."""
        self._recipes[recipe.name] = recipe

    def get(self, pattern_name: str) -> Recipe | None:
        """Look up a recipe by pattern name. Returns None if not found."""
        return self._recipes.get(pattern_name)

    def list_all(self) -> list[Recipe]:
        """List all registered recipes."""
        return list(self._recipes.values())

    def known_patterns(self) -> set[str]:
        """Return the set of known pattern names."""
        return set(self._recipes.keys())


def create_default_registry() -> RecipeRegistry:
    """Create a registry with all default MVP recipes registered."""
    registry = RecipeRegistry()
    registry.register(DirectSignalMappingRecipe())
    registry.register(ToggleButtonStateRecipe())
    registry.register(PeriodicBlinkingOutputRecipe())
    return registry
