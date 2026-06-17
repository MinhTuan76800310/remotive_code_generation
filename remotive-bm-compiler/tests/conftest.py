"""Shared test fixtures for the Remotive Behavioral Model Compiler test suite."""

import os
import tempfile

import pytest

from bmgen.ir.builder import build_ir
from bmgen.ir.model import (
    BehavioralModelIR,
    HandlerIR,
    InputSignalIR,
    NamespaceIR,
    OutputSignalIR,
    RestbusConfigIR,
    StateIR,
)
from bmgen.ir.parser import parse_yaml_string


@pytest.fixture
def bcm_direct_yaml():
    """YAML spec for a simple DirectSignalMapping BCM model."""
    return """
model:
  name: BCM
  ecu_name: BCM

namespaces:
  - name: BCM-BodyCan0
    type: can
    role: output
    restbus:
      sender_filter: BCM
  - name: BCM-DriverCan0
    type: can
    role: input

handlers:
  - name: on_hazard_light
    pattern: DirectSignalMapping
    input:
      namespace: BCM-DriverCan0
      frame_filter: HazardLightButton
      signal: HazardLightButton.HazardLightButton
    output:
      namespace: BCM-BodyCan0
      signals:
        - TurnLightControl.RightTurnLightRequest
        - TurnLightControl.LeftTurnLightRequest
"""


@pytest.fixture
def bcm_toggle_yaml():
    """YAML spec for a ToggleButtonState BCM model."""
    return """
model:
  name: BCM
  ecu_name: BCM

namespaces:
  - name: BCM-BodyCan0
    type: can
    role: output
    restbus:
      sender_filter: BCM
  - name: BCM-DriverCan0
    type: can
    role: input

handlers:
  - name: on_hazard_button
    pattern: ToggleButtonState
    input:
      namespace: BCM-DriverCan0
      frame_filter: HazardLightButton
      signal: HazardLightButton.HazardLightButton
    output:
      namespace: BCM-BodyCan0
      signals:
        - TurnLightControl.RightTurnLightRequest
        - TurnLightControl.LeftTurnLightRequest
    state:
      name: hazard_enabled
      type: bool
      initial: false
      reset_value: false
      owner: on_hazard_button

reset_handler: true
"""


@pytest.fixture
def bcm_direct_ir(bcm_direct_yaml):
    """Validated BehavioralModelIR for the DirectSignalMapping BCM model."""
    spec = parse_yaml_string(bcm_direct_yaml)
    return build_ir(spec)


@pytest.fixture
def bcm_toggle_ir(bcm_toggle_yaml):
    """Validated BehavioralModelIR for the ToggleButtonState BCM model."""
    spec = parse_yaml_string(bcm_toggle_yaml)
    return build_ir(spec)


@pytest.fixture
def temp_output_dir():
    """Temporary directory for generated code output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir
