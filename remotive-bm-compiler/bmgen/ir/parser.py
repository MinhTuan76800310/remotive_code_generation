"""YAML spec parser — reads a YAML file and returns a raw Python dict.

This module handles the pure parsing step: YAML text → Python dict.
No validation is performed here; that happens in validators.py after
the dict is converted to IR dataclasses by builder.py.
"""

from __future__ import annotations

import yaml


def parse_yaml_file(path: str) -> dict:
    """Parse a YAML spec file and return the raw Python dict.

    Args:
        path: Path to the YAML file.

    Returns:
        Raw Python dict representing the YAML spec.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        yaml.YAMLError: If the YAML syntax is invalid.
    """
    with open(path) as f:
        content = f.read()

    data = yaml.safe_load(content)

    if data is None:
        raise ValueError(f"YAML file '{path}' is empty or contains only null values")

    if not isinstance(data, dict):
        raise ValueError(f"YAML file '{path}' must contain a mapping (dict), got {type(data).__name__}")

    return data


def parse_yaml_string(content: str) -> dict:
    """Parse a YAML string and return the raw Python dict.

    Args:
        content: YAML string content.

    Returns:
        Raw Python dict representing the YAML spec.

    Raises:
        yaml.YAMLError: If the YAML syntax is invalid.
    """
    data = yaml.safe_load(content)

    if data is None:
        raise ValueError("YAML content is empty or contains only null values")

    if not isinstance(data, dict):
        raise ValueError(f"YAML content must contain a mapping (dict), got {type(data).__name__}")

    return data
