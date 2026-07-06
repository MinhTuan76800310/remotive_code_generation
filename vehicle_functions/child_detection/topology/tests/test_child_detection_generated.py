"""E2E tests for bmgen output — same style as getting_started/tests/test_hazard_light.py.

Topology source: vehicle_functions/child_detection/topology/
Models under test: copied from vehicle_functions/child_detection/generated/ (sync via
../sync-generated-to-topology.sh after bmgen generate).

CAD logic (inc_schema/SWC_CAD_logic.yaml):
  weights: SeatInput=1, Camera=1, AirbagStatusReport=2
  threshold: 3.0
  alert ON iff weighted_sum >= 3.0

Chain:
  SEAT  WeightKg -> SeatOccupied
  DMS   CameraInput (restbus inject in tests; prod uses WS)
  AIRBAG AirbagStatusSensor -> AirbagStatusReport
  CENTRAL WeightedLogOdds -> ChildAlert
  COCKPIT -> HmiChildWarning
"""

from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from remotivelabs.broker import BrokerClient, RestbusSignalConfig
from remotivelabs.topology.behavioral_model import PingRequest
from remotivelabs.topology.control import ControlClient
from remotivelabs.topology.testing.frames import capture_frames


@pytest_asyncio.fixture()
async def broker_client(request: pytest.FixtureRequest) -> AsyncIterator[BrokerClient]:
    url = request.config.getoption("broker_url")
    async with BrokerClient(url=url) as broker_client, ControlClient(broker_client) as cc:
        for ecu in ("SEAT", "DMS", "CENTRAL", "COCKPIT", "AIRBAG"):
            await cc.send(target_ecu=ecu, request=PingRequest(), timeout=1, retries=20)
        yield broker_client


async def _inject_seat(broker: BrokerClient, weight_kg: float) -> None:
    await broker.restbus.update_signals(
        ("SEAT-CpdCan0", [RestbusSignalConfig.set(name="SeatWeightSensor.WeightKg", value=weight_kg)])
    )


async def _inject_camera(broker: BrokerClient, child_detected: int) -> None:
    await broker.restbus.update_signals(
        (
            "DMS-CpdCan0",
            [RestbusSignalConfig.set(name="CameraInput.ChildDetectedByCamera", value=child_detected)],
        )
    )


async def _inject_airbag_status_sensor(broker: BrokerClient, status: int) -> None:
    """AIRBAG model maps AirbagStatusSensor -> AirbagStatusReport for CENTRAL fan-in."""
    await broker.restbus.update_signals(
        (
            "AIRBAG-CpdCan0",
            [RestbusSignalConfig.set(name="AirbagStatusSensor.AirbagStatus", value=status)],
        )
    )


@pytest.mark.asyncio
@pytest.mark.timeout(20, func_only=True)
async def test_child_alert_when_seat_camera_and_airbag_status_agree(broker_client: BrokerClient):
    # seat=1, cam=1, airbag=1 -> 1+1+2 = 4 >= 3
    await _inject_seat(broker_client, 4.0)
    await _inject_camera(broker_client, 1)
    await _inject_airbag_status_sensor(broker_client, 1)

    async with capture_frames((broker_client, "COCKPIT-CpdCan0"), ["HmiChildWarning"]) as cap:
        await cap.wait_for_frame(
            "HmiChildWarning",
            {"HmiChildWarning.ChildAlertActive": 1.0},
            timeout=15,
        )


@pytest.mark.asyncio
@pytest.mark.timeout(20, func_only=True)
async def test_child_alert_at_threshold_without_seat(broker_client: BrokerClient):
    # seat=0, cam=1, airbag=1 -> 0+1+2 = 3 >= 3 (boundary)
    await _inject_seat(broker_client, 75.0)
    await _inject_camera(broker_client, 1)
    await _inject_airbag_status_sensor(broker_client, 1)

    async with capture_frames((broker_client, "COCKPIT-CpdCan0"), ["HmiChildWarning"]) as cap:
        await cap.wait_for_frame(
            "HmiChildWarning",
            {"HmiChildWarning.ChildAlertActive": 1.0},
            timeout=15,
        )


@pytest.mark.asyncio
@pytest.mark.timeout(20, func_only=True)
async def test_no_alert_when_sum_below_threshold(broker_client: BrokerClient):
    # seat=1, cam=1, airbag=0 -> 1+1+0 = 2 < 3
    await _inject_seat(broker_client, 4.0)
    await _inject_camera(broker_client, 1)
    await _inject_airbag_status_sensor(broker_client, 0)

    async with capture_frames((broker_client, "COCKPIT-CpdCan0"), ["HmiChildWarning"]) as cap:
        await cap.wait_for_frame(
            "HmiChildWarning",
            {"HmiChildWarning.ChildAlertActive": 0.0},
            timeout=15,
        )


@pytest.mark.asyncio
@pytest.mark.timeout(30, func_only=True)
async def test_driver_turn_airbag_off_propagates_to_actuator(broker_client: BrokerClient):
    await _inject_seat(broker_client, 4.0)
    await _inject_camera(broker_client, 1)
    await _inject_airbag_status_sensor(broker_client, 1)

    await broker_client.restbus.update_signals(
        ("COCKPIT-CpdCan0", [RestbusSignalConfig.set(name="HmiDriverAction.TurnAirbagOff", value=1)])
    )

    async with capture_frames((broker_client, "AIRBAG-CpdCan0"), ["AirbagActuatorState"]) as cap:
        await cap.wait_for_frame(
            "AirbagActuatorState",
            {"AirbagActuatorState.AirbagActuated": 1.0},
            timeout=25,
        )