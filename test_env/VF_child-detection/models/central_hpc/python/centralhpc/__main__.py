import asyncio
import logging
from dataclasses import dataclass

from remotivelabs.broker import BrokerClient, Frame
from remotivelabs.topology.behavioral_model import BehavioralModel
from remotivelabs.topology.cli.behavioral_model import BehavioralModelArgs
from remotivelabs.topology.namespaces import filters
from remotivelabs.topology.namespaces.can import CanNamespace, RestbusConfig

@dataclass
class CentralHPC:
    cpd_can_0: CanNamespace
    dms_cpd_can_0: CanNamespace
    _seat_input_latched: bool = False
    _camera_input_child_detected_by_camera_latched: bool = False
    _camera_input_is_moving_latched: bool = False

    async def CAD_logic(self, frame: Frame) -> None:
        if "SeatInput.SeatOccupied" in frame.signals:
            self._seat_input_latched = bool(frame.signals["SeatInput.SeatOccupied"])
        if "CameraInput.ChildDetectedByCamera" in frame.signals:
            self._camera_input_child_detected_by_camera_latched = bool(frame.signals["CameraInput.ChildDetectedByCamera"])
        if "CameraInput.IsMoving" in frame.signals:
            self._camera_input_is_moving_latched = bool(frame.signals["CameraInput.IsMoving"])
        _weighted_sum = (0.3 * (1 if _seat_input_latched else 0)) + (0.7 * (1 if _camera_input_child_detected_by_camera_latched else 0)) + (0.3 * (1 if _camera_input_is_moving_latched else 0))
        await self.cpd_can_0.restbus.update_signals(
            ("ChildAlert.ChildAlertActive", 1 if _weighted_sum >= 1.0 else 0),
        )

    async def Driver_Decision_Routing(self, frame: Frame) -> None:
        driver_decision_signal = frame.signals["DriverDecision.TurnAirbagOff"]
        await self.cpd_can_0.restbus.update_signals(
            ("AirbagControlCommand.AirbagControlCommand", driver_decision_signal),
        )



async def main(avp: BehavioralModelArgs):
    logging.info("Starting CentralHPC simulator")

    async with BrokerClient(url=avp.url, auth=avp.auth) as broker_client:
        cpd_can_0 = CanNamespace(
            "CENTRAL-CpdCan0",
            broker_client,
            restbus_configs=[RestbusConfig([filters.SenderFilter(ecu_name="CENTRAL")], delay_multiplier=avp.delay_multiplier)],
        )

        dms_cpd_can_0 = CanNamespace("DMS-CpdCan0", broker_client)

        centralhpc = CentralHPC(
            cpd_can_0=cpd_can_0,
            dms_cpd_can_0=dms_cpd_can_0,
        )

        async with BehavioralModel(
            "CENTRAL",
            namespaces=[cpd_can_0, dms_cpd_can_0],
            broker_client=broker_client,
            input_handlers=[
                cpd_can_0.create_input_handler(
                    [filters.FrameFilter("SeatInput")],
                    centralhpc.CAD_logic,
                ),
                dms_cpd_can_0.create_input_handler(
                    [filters.FrameFilter("CameraInput")],
                    centralhpc.CAD_logic,
                ),
                dms_cpd_can_0.create_input_handler(
                    [filters.FrameFilter("CameraInput")],
                    centralhpc.CAD_logic,
                ),
                cpd_can_0.create_input_handler(
                    [filters.FrameFilter("DriverDecision")],
                    centralhpc.Driver_Decision_Routing,
                ),
            ],
        ) as bm:
            await bm.run_forever()


if __name__ == "__main__":
    args = BehavioralModelArgs.parse()
    logging.basicConfig(level=args.loglevel)
    logging.getLogger("remotivelabs.topology").setLevel(logging.DEBUG)
    asyncio.run(main(args))
