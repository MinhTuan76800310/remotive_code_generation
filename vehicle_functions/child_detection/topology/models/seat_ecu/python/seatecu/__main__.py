import asyncio
import logging
from dataclasses import dataclass

from remotivelabs.broker import BrokerClient, Frame
from remotivelabs.topology.behavioral_model import BehavioralModel
from remotivelabs.topology.cli.behavioral_model import BehavioralModelArgs
from remotivelabs.topology.namespaces import filters
from remotivelabs.topology.namespaces.can import CanNamespace, RestbusConfig

@dataclass
class SeatECU:
    cpd_can_0: CanNamespace

    async def Seat_Sensors_Preprocessing(self, frame: Frame) -> None:
        seat_weight_sensor_signal = frame.signals["SeatWeightSensor.WeightKg"]
        await self.cpd_can_0.restbus.update_signals(
            ("SeatInput.SeatOccupied", 1 if not (seat_weight_sensor_signal >= 8.0) else 0),
        )



async def main(avp: BehavioralModelArgs):
    logging.info("Starting SeatECU simulator")

    async with BrokerClient(url=avp.url, auth=avp.auth) as broker_client:
        cpd_can_0 = CanNamespace(
            "SEAT-CpdCan0",
            broker_client,
            restbus_configs=[RestbusConfig([filters.SenderFilter(ecu_name="SEAT")], delay_multiplier=avp.delay_multiplier)],
        )

        seatecu = SeatECU(
            cpd_can_0=cpd_can_0,
        )

        async with BehavioralModel(
            "SEAT",
            namespaces=[cpd_can_0],
            broker_client=broker_client,
            input_handlers=[
                cpd_can_0.create_input_handler(
                    [filters.FrameFilter("SeatWeightSensor")],
                    seatecu.Seat_Sensors_Preprocessing,
                ),
            ],
        ) as bm:
            await bm.run_forever()


if __name__ == "__main__":
    args = BehavioralModelArgs.parse()
    logging.basicConfig(level=args.loglevel)
    logging.getLogger("remotivelabs.topology").setLevel(logging.DEBUG)
    asyncio.run(main(args))
