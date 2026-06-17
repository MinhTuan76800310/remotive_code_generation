import asyncio
import logging
from dataclasses import dataclass

from remotivelabs.broker import BrokerClient, Frame
from remotivelabs.topology.behavioral_model import BehavioralModel
from remotivelabs.topology.cli.behavioral_model import BehavioralModelArgs
from remotivelabs.topology.namespaces import filters
from remotivelabs.topology.namespaces.can import CanNamespace, RestbusConfig


@dataclass
class BCM:
    body_can_0: CanNamespace

    async def on_hazard_light(self, frame: Frame) -> None:
        hazard_light_button_signal = frame.signals["HazardLightButton.HazardLightButton"]
        await self.body_can_0.restbus.update_signals(
            ("TurnLightControl.RightTurnLightRequest", hazard_light_button_signal),
            ("TurnLightControl.LeftTurnLightRequest", hazard_light_button_signal),
        )



async def main(avp: BehavioralModelArgs):
    logging.info("Starting BCM simulator")

    async with BrokerClient(url=avp.url, auth=avp.auth) as broker_client:
        body_can_0 = CanNamespace(
            "BCM-BodyCan0",
            broker_client,
            restbus_configs=[RestbusConfig([filters.SenderFilter(ecu_name="BCM")], delay_multiplier=avp.delay_multiplier)],
        )

        driver_can_0 = CanNamespace("BCM-DriverCan0", broker_client)

        bcm = BCM(
            body_can_0=body_can_0,
        )

        async with BehavioralModel(
            "BCM",
            namespaces=[body_can_0, driver_can_0],
            broker_client=broker_client,
            input_handlers=[
                driver_can_0.create_input_handler(
                    [filters.FrameFilter("HazardLightButton")],
                    bcm.on_hazard_light,
                ),
            ],
        ) as bm:
            await bm.run_forever()


if __name__ == "__main__":
    args = BehavioralModelArgs.parse()
    logging.basicConfig(level=args.loglevel)
    logging.getLogger("remotivelabs.topology").setLevel(logging.DEBUG)
    asyncio.run(main(args))
