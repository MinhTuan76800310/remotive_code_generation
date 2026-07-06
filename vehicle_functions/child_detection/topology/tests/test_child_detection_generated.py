"""E2E: stimulus from input ECUs (restbus) → oracle on output frame (getting_started pattern).

Method (K-map / truth table):
  1. Map physical inputs to booleans p_seat, p_cam, p_airbag (via SEAT weight, DMS camera, AIRBAG sensor).
  2. expected_alert = 1 if (1*p_seat + 1*p_cam + 2*p_airbag) >= 3.0 else 0  (inc_schema CAD_logic).
  3. actual = COCKPIT-CpdCan0 HmiChildWarning.ChildAlertActive (downstream of CENTRAL ChildAlert).

Sync models: vehicle_functions/child_detection/sync-generated-to-test_env.sh
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

import pytest
import pytest_asyncio
from remotivelabs.broker import BrokerClient, RestbusSignalConfig
from remotivelabs.topology.behavioral_model import PingRequest
from remotivelabs.topology.control import ControlClient
from remotivelabs.topology.testing.frames import capture_frames

W_SEAT = 1.0
W_CAM = 1.0
W_AIRBAG = 2.0
THRESHOLD = 3.0


def cad_weighted_sum(p_seat: int, p_cam: int, p_airbag: int) -> float:
    return W_SEAT * p_seat + W_CAM * p_cam + W_AIRBAG * p_airbag


def cad_expected(p_seat: int, p_cam: int, p_airbag: int) -> float:
    return 1.0 if cad_weighted_sum(p_seat, p_cam, p_airbag) >= THRESHOLD else 0.0


@dataclass(frozen=True)
class CadKmapRow:
    id: str
    weight_kg: float
    child_detected: int
    airbag_status: int
    p_seat: int
    p_cam: int
    p_airbag: int

    @property
    def expected_alert(self) -> float:
        return cad_expected(self.p_seat, self.p_cam, self.p_airbag)


# Full 2^3 K-map for active CAD inputs in inc_schema (IsMoving not in spec).
CAD_KMAP: tuple[CadKmapRow, ...] = (
    CadKmapRow("km_000", 75.0, 0, 0, 0, 0, 0),
    CadKmapRow("km_001", 75.0, 0, 1, 0, 0, 1),
    CadKmapRow("km_010", 75.0, 1, 0, 0, 1, 0),
    CadKmapRow("km_011", 75.0, 1, 1, 0, 1, 1),  # sum=3 boundary ON without seat
    CadKmapRow("km_100", 4.0, 0, 0, 1, 0, 0),
    CadKmapRow("km_101", 4.0, 0, 1, 1, 0, 1),
    CadKmapRow("km_110", 4.0, 1, 0, 1, 1, 0),
    CadKmapRow("km_111", 4.0, 1, 1, 1, 1, 1),  # sum=4 ON
)


def _log_kmap_case(row: CadKmapRow, actual: float, frame_name: str) -> None:
    wsum = cad_weighted_sum(row.p_seat, row.p_cam, row.p_airbag)
    exp = row.expected_alert
    ok = actual == exp
    print(
        f"\n{'=' * 72}\n"
        f"  K-map case : {row.id}\n"
        f"  INJECT     : SEAT WeightKg={row.weight_kg}  "
        f"DMS ChildDetected={row.child_detected}  "
        f"AIRBAG AirbagStatusSensor={row.airbag_status}\n"
        f"  BOOLS      : p_seat={row.p_seat}  p_cam={row.p_cam}  p_airbag={row.p_airbag}\n"
        f"  CAD_LOGIC  : sum = 1·{row.p_seat} + 1·{row.p_cam} + 2·{row.p_airbag} = {wsum:.1f}  "
        f"(threshold {THRESHOLD})\n"
        f"  EXPECTED   : HmiChildWarning.ChildAlertActive = {exp:.0f}  "
        f"({'ALERT ON' if exp else 'ALERT OFF'})\n"
        f"  ACTUAL     : {frame_name}.ChildAlertActive = {actual:.0f}\n"
        f"  RESULT     : {'MATCH' if ok else 'MISMATCH'}\n"
        f"{'=' * 72}",
        flush=True,
    )


@pytest_asyncio.fixture()
async def broker_client(request: pytest.FixtureRequest) -> AsyncIterator[BrokerClient]:
    url = request.config.getoption("broker_url")
    async with BrokerClient(url=url) as broker_client, ControlClient(broker_client) as cc:
        for ecu in ("SEAT", "DMS", "CENTRAL", "COCKPIT", "AIRBAG"):
            await cc.send(target_ecu=ecu, request=PingRequest(), timeout=1, retries=20)
        yield broker_client


async def _apply_inputs(
    broker: BrokerClient,
    weight_kg: float,
    child_detected: int,
    airbag_status: int,
) -> None:
    await broker.restbus.update_signals(
        ("SEAT-CpdCan0", [RestbusSignalConfig.set(name="SeatWeightSensor.WeightKg", value=weight_kg)])
    )
    await broker.restbus.update_signals(
        (
            "DMS-CpdCan0",
            [RestbusSignalConfig.set(name="CameraInput.ChildDetectedByCamera", value=child_detected)],
        )
    )
    await broker.restbus.update_signals(
        (
            "AIRBAG-CpdCan0",
            [RestbusSignalConfig.set(name="AirbagStatusSensor.AirbagStatus", value=airbag_status)],
        )
    )


@pytest.mark.asyncio
@pytest.mark.timeout(25, func_only=True)
@pytest.mark.parametrize("row", CAD_KMAP, ids=[r.id for r in CAD_KMAP])
async def test_cad_kmap_expected_matches_hmi_actual(broker_client: BrokerClient, row: CadKmapRow):
    print(f"\n>>> Running K-map E2E: {row.id}", flush=True)
    await _apply_inputs(broker_client, row.weight_kg, row.child_detected, row.airbag_status)

    async with capture_frames((broker_client, "COCKPIT-CpdCan0"), ["HmiChildWarning"]) as cap:
        frame = await cap.wait_for_frame(
            "HmiChildWarning",
            {"HmiChildWarning.ChildAlertActive": row.expected_alert},
            timeout=18,
        )
    actual = float(frame.signals["HmiChildWarning.ChildAlertActive"])
    _log_kmap_case(row, actual, "HmiChildWarning")
    assert actual == row.expected_alert, (
        f"{row.id}: expected ChildAlertActive={row.expected_alert}, got {actual}"
    )


@pytest.mark.asyncio
@pytest.mark.timeout(30, func_only=True)
async def test_driver_turn_airbag_off_propagates_to_actuator(broker_client: BrokerClient):
    row = next(r for r in CAD_KMAP if r.id == "km_111")
    print("\n>>> Running airbag chain E2E (after km_111 alert)", flush=True)
    await _apply_inputs(broker_client, row.weight_kg, row.child_detected, row.airbag_status)

    await broker_client.restbus.update_signals(
        ("COCKPIT-CpdCan0", [RestbusSignalConfig.set(name="HmiDriverAction.TurnAirbagOff", value=1)])
    )
    print("  INJECT     : COCKPIT HmiDriverAction.TurnAirbagOff = 1", flush=True)
    print("  EXPECTED   : AIRBAG AirbagActuatorState.AirbagActuated = 1", flush=True)

    async with capture_frames((broker_client, "AIRBAG-CpdCan0"), ["AirbagActuatorState"]) as cap:
        frame = await cap.wait_for_frame(
            "AirbagActuatorState",
            {"AirbagActuatorState.AirbagActuated": 1.0},
            timeout=25,
        )
    actual = float(frame.signals["AirbagActuatorState.AirbagActuated"])
    print(f"  ACTUAL     : AirbagActuatorState.AirbagActuated = {actual:.0f}", flush=True)
    print(f"  RESULT     : {'MATCH' if actual == 1.0 else 'MISMATCH'}\n", flush=True)
    assert actual == 1.0