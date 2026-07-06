import asyncio
import logging
from dataclasses import dataclass

from remotivelabs.broker import BrokerClient, Frame
from remotivelabs.topology.behavioral_model import BehavioralModel
from remotivelabs.topology.cli.behavioral_model import BehavioralModelArgs
from remotivelabs.topology.namespaces import filters
from remotivelabs.topology.namespaces.can import CanNamespace, RestbusConfig

@dataclass
class CockpitHMIECU:
    cpd_can_0: CanNamespace

    async def Child_Alert_Forward(self, frame: Frame) -> None:
        child_alert_signal = frame.signals["ChildAlert.ChildAlertActive"]
        await self.cpd_can_0.restbus.update_signals(
            ("HmiChildWarning.ChildAlertActive", child_alert_signal),
        )

    async def Driver_Action_Publish(self, frame: Frame) -> None:
        hmi_driver_action_signal = frame.signals["HmiDriverAction.TurnAirbagOff"]
        await self.cpd_can_0.restbus.update_signals(
            ("DriverDecision.TurnAirbagOff", hmi_driver_action_signal),
        )



async def main(avp: BehavioralModelArgs):
    logging.info("Starting CockpitHMIECU simulator")

    async with BrokerClient(url=avp.url, auth=avp.auth) as broker_client:
        cpd_can_0 = CanNamespace(
            "COCKPIT-CpdCan0",
            broker_client,
            restbus_configs=[RestbusConfig([filters.SenderFilter(ecu_name="COCKPIT")], delay_multiplier=avp.delay_multiplier)],
        )

        cockpithmiecu = CockpitHMIECU(
            cpd_can_0=cpd_can_0,
        )

        async with BehavioralModel(
            "COCKPIT",
            namespaces=[cpd_can_0],
            broker_client=broker_client,
            input_handlers=[
                cpd_can_0.create_input_handler(
                    [filters.FrameFilter("ChildAlert")],
                    cockpithmiecu.Child_Alert_Forward,
                ),
                cpd_can_0.create_input_handler(
                    [filters.FrameFilter("HmiDriverAction")],
                    cockpithmiecu.Driver_Action_Publish,
                ),
            ],
        ) as bm:
            await bm.run_forever()


if __name__ == "__main__":
    args = BehavioralModelArgs.parse()
    logging.basicConfig(level=args.loglevel)
    logging.getLogger("remotivelabs.topology").setLevel(logging.DEBUG)
    asyncio.run(main(args))
