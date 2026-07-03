"""Integration tests for the VF child-detection topology.

Chain under test (all on single shared CpdCan0 channel):
    SEAT  (SeatWeightSensor.WeightKg  -> SeatInput.SeatOccupied)               # weight < 8kg = child
    DMS   (camera websocket -> CameraInput.ChildDetectedByCamera,
                                          CameraInput.IsMoving)                 # from camera/ws
        |
        v
    CENTRAL (WeightedLogOdds: 0.7*cam + 0.3*seat + 0.3*mov >= 1.0
                              -> ChildAlert.ChildAlertActive)
        |
        v
    COCKPIT (ChildAlert -> HmiChildWarning.ChildAlertActive)
        |
        v  (driver confirms: HmiDriverAction.TurnAirbagOff -> DriverDecision.TurnAirbagOff)
    CENTRAL (DriverDecision -> AirbagControlCommand.AirbagControlCommand)
        |
        v
    AIRBAG  (AirbagControlCommand -> AirbagActuatorState.AirbagActuated)

The DMS model normally consumes the camera websocket (ws://localhost:1122).
For deterministic testing we inject ChildDetectedByCamera AND IsMoving
directly on the DMS-CpdCan0 restbus — the broker routes them to CENTRAL
exactly as the websocket bridge would. The camera service does NOT need
to be running during the pytest run.
"""

from typing import AsyncIterator

import pytest
import pytest_asyncio
from remotivelabs.broker import BrokerClient, RestbusSignalConfig
from remotivelabs.topology.behavioral_model import PingRequest
from remotivelabs.topology.control import ControlClient
from remotivelabs.topology.testing.frames import capture_frames


@pytest_asyncio.fixture()
async def broker_client(request: pytest.FixtureRequest) -> AsyncIterator[BrokerClient]:
    """Connect to the broker and ping every ECU to confirm all models are up."""
    url = request.config.getoption("broker_url")
    async with BrokerClient(url=url) as broker_client, ControlClient(broker_client) as cc:
        for ecu in ("SEAT", "DMS", "CENTRAL", "COCKPIT", "AIRBAG"):
            await cc.send(target_ecu=ecu, request=PingRequest(), timeout=1, retries=20)
        yield broker_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# Truth table reference (weights [Seat=0.3, Camera=0.7, IsMoving=0.3], threshold 1.0):
#   seat cam mov | sum  | alert
#   0   0   0    | 0.0  | OFF
#   1   0   0    | 0.3  | OFF
#   0   1   0    | 0.7  | OFF
#   0   0   1    | 0.3  | OFF
#   1   1   0    | 1.0  | ON
#   1   0   1    | 0.6  | OFF
#   0   1   1    | 1.0  | ON
#   1   1   1    | 1.3  | ON


async def _inject_seat(broker: BrokerClient, weight_kg: float) -> None:
    await broker.restbus.update_signals(
        ("SEAT-CpdCan0", [RestbusSignalConfig.set(name="SeatWeightSensor.WeightKg", value=weight_kg)])
    )


async def _inject_camera(broker: BrokerClient, child_detected: int, is_moving: int) -> None:
    """Push both camera fields onto the DMS-CpdCan0 restbus in one call."""
    await broker.restbus.update_signals(
        ("DMS-CpdCan0", [
            RestbusSignalConfig.set(name="CameraInput.ChildDetectedByCamera", value=child_detected),
            RestbusSignalConfig.set(name="CameraInput.IsMoving",             value=is_moving),
        ])
    )


# ---------------------------------------------------------------------------
# Positive path: seat=light + camera=child + moving=true => sum=1.3 => Alert ON
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.timeout(20, func_only=True)
async def test_child_alert_when_seat_and_camera_and_moving_agree(broker_client: BrokerClient):
    # seat=1, cam=1, mov=1 → sum 1.3 ≥ 1.0 ⇒ ON
    await _inject_seat(broker_client, 4.0)
    await _inject_camera(broker_client, child_detected=1, is_moving=1)

    async with capture_frames((broker_client, "COCKPIT-CpdCan0"), ["HmiChildWarning"]) as cap:
        await cap.wait_for_frame(
            "HmiChildWarning",
            {"HmiChildWarning.ChildAlertActive": 1.0},
            timeout=15,
        )


# ---------------------------------------------------------------------------
# Negative path: seat=adult + camera=child + moving=false => sum=0.7 => Alert OFF
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.timeout(20, func_only=True)
async def test_no_alert_when_seat_weight_is_adult_and_no_motion(broker_client: BrokerClient):
    # seat=0, cam=1, mov=0 → sum 0.7 < 1.0 ⇒ OFF
    await _inject_seat(broker_client, 75.0)
    await _inject_camera(broker_client, child_detected=1, is_moving=0)

    async with capture_frames((broker_client, "COCKPIT-CpdCan0"), ["HmiChildWarning"]) as cap:
        await cap.wait_for_frame(
            "HmiChildWarning",
            {"HmiChildWarning.ChildAlertActive": 0.0},
            timeout=15,
        )


# ---------------------------------------------------------------------------
# WeightedLogOdds edge case: camera + motion WITHOUT seat (sum=1.0 == threshold) ⇒ ON
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.timeout(20, func_only=True)
async def test_child_alert_threshold_from_camera_alone(broker_client: BrokerClient):
    # seat=0, cam=1, mov=1 → sum 1.0 ≥ 1.0 ⇒ ON (camera + motion, no seat signal)
    await _inject_seat(broker_client, 75.0)
    await _inject_camera(broker_client, child_detected=1, is_moving=1)

    async with capture_frames((broker_client, "COCKPIT-CpdCan0"), ["HmiChildWarning"]) as cap:
        await cap.wait_for_frame(
            "HmiChildWarning",
            {"HmiChildWarning.ChildAlertActive": 1.0},
            timeout=15,
        )


# ---------------------------------------------------------------------------
# WeightedLogOdds edge case: light seat ALONE is not enough (sum=0.3 < threshold) ⇒ OFF
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.timeout(20, func_only=True)
async def test_no_alert_when_only_seat_signal_fires(broker_client: BrokerClient):
    # seat=1, cam=0, mov=0 → sum 0.3 < 1.0 ⇒ OFF
    await _inject_seat(broker_client, 4.0)
    await _inject_camera(broker_client, child_detected=0, is_moving=0)

    async with capture_frames((broker_client, "COCKPIT-CpdCan0"), ["HmiChildWarning"]) as cap:
        await cap.wait_for_frame(
            "HmiChildWarning",
            {"HmiChildWarning.ChildAlertActive": 0.0},
            timeout=15,
        )


# ---------------------------------------------------------------------------
# Full airbag-deactivation path: alert → driver turns airbag off → AIRBAG actuates
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.timeout(30, func_only=True)
async def test_driver_confirms_airbag_off_propagates_to_airbag(broker_client: BrokerClient):
    # 1. Trigger a child alert (light seat + camera detects + moving).
    await _inject_seat(broker_client, 3.0)
    await _inject_camera(broker_client, child_detected=1, is_moving=1)

    # 2. Driver chooses "Turn Airbag OFF" on the HMI surface.
    await broker_client.restbus.update_signals(
        ("COCKPIT-CpdCan0", [RestbusSignalConfig.set(name="HmiDriverAction.TurnAirbagOff", value=1)])
    )

    # 3. COCKPIT -> DriverDecision -> CENTRAL -> AirbagControlCommand -> AIRBAG actuator.
    async with capture_frames((broker_client, "AIRBAG-CpdCan0"), ["AirbagActuatorState"]) as cap:
        await cap.wait_for_frame(
            "AirbagActuatorState",
            {"AirbagActuatorState.AirbagActuated": 1.0},
            timeout=25,
        )
