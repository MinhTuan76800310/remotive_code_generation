import asyncio
import logging
from dataclasses import dataclass

from remotivelabs.broker import BrokerClient, Frame
from remotivelabs.topology.behavioral_model import BehavioralModel
from remotivelabs.topology.cli.behavioral_model import BehavioralModelArgs
from remotivelabs.topology.namespaces import filters
from remotivelabs.topology.namespaces.can import CanNamespace, RestbusConfig

@dataclass
class AirbagControlUnit:
    cpd_can_0: CanNamespace

    async def Provide_Airbag_Status(self, frame: Frame) -> None:
        airbag_status_sensor_signal = frame.signals["AirbagStatusSensor.AirbagStatus"]
        await self.cpd_can_0.restbus.update_signals(
            ("AirbagStatusReport.AirbagStatus", airbag_status_sensor_signal),
        )

    async def Apply_Airbag_Control_Command(self, frame: Frame) -> None:
        airbag_control_command_signal = frame.signals["AirbagControlCommand.AirbagControlCommand"]
        await self.cpd_can_0.restbus.update_signals(
            ("AirbagActuatorState.AirbagActuated", airbag_control_command_signal),
        )



async def main(avp: BehavioralModelArgs):
    logging.info("Starting AirbagControlUnit simulator")

    async with BrokerClient(url=avp.url, auth=avp.auth) as broker_client:
        cpd_can_0 = CanNamespace(
            "AIRBAG-CpdCan0",
            broker_client,
            restbus_configs=[RestbusConfig([filters.SenderFilter(ecu_name="AIRBAG")], delay_multiplier=avp.delay_multiplier)],
        )

        airbagcontrolunit = AirbagControlUnit(
            cpd_can_0=cpd_can_0,
        )

        async with BehavioralModel(
            "AIRBAG",
            namespaces=[cpd_can_0],
            broker_client=broker_client,
            input_handlers=[
                cpd_can_0.create_input_handler(
                    [filters.FrameFilter("AirbagStatusSensor")],
                    airbagcontrolunit.Provide_Airbag_Status,
                ),
                cpd_can_0.create_input_handler(
                    [filters.FrameFilter("AirbagControlCommand")],
                    airbagcontrolunit.Apply_Airbag_Control_Command,
                ),
            ],
        ) as bm:
            await bm.run_forever()


if __name__ == "__main__":
    args = BehavioralModelArgs.parse()
    logging.basicConfig(level=args.loglevel)
    logging.getLogger("remotivelabs.topology").setLevel(logging.DEBUG)
    asyncio.run(main(args))
