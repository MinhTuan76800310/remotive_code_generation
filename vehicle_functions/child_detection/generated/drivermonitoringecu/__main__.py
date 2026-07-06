import asyncio
import logging
from dataclasses import dataclass

from remotivelabs.broker import BrokerClient, Frame
from remotivelabs.topology.behavioral_model import BehavioralModel
from remotivelabs.topology.cli.behavioral_model import BehavioralModelArgs
from remotivelabs.topology.namespaces import filters
from remotivelabs.topology.namespaces.can import CanNamespace, RestbusConfig
import json

import websockets

@dataclass
class DriverMonitoringECU:
    cpd_can_0: CanNamespace
    _ws_task_camera_data_preprocessing: asyncio.Task | None = None

    def _start_ws_camera_data_preprocessing(self) -> None:
        """Launch the websocket bridge camera_data_preprocessing as a background task."""
        self._ws_task_camera_data_preprocessing = asyncio.create_task(self._ws_loop_camera_data_preprocessing())

    def _stop_ws_camera_data_preprocessing(self) -> None:
        """Cancel the websocket bridge camera_data_preprocessing (no-op if not running)."""
        if self._ws_task_camera_data_preprocessing:
            self._ws_task_camera_data_preprocessing.cancel()
        self._ws_task_camera_data_preprocessing = None

    async def _ws_loop_camera_data_preprocessing(self) -> None:
        """Read ws://localhost:1122 forever and forward JSON values to the DMS-CpdCan0 restbus.

        Each incoming message is decoded as JSON. For every (ws_key, restbus_signal)
        pair in the signal map, the value at ws_key is published to the matching
        restbus signal. On disconnect/error a warning is logged and the listener
        reconnects after 2.0s.
        """
        ws_url = "ws://localhost:1122"
        signal_map = [
            ("ChildDetected", "CameraInput.ChildDetectedByCamera"),
        ]
        while True:
            try:
                async with websockets.connect(ws_url) as ws:
                    logging.info("ws bridge camera_data_preprocessing connected: %s", ws_url)
                    async for raw in ws:
                        payload = json.loads(raw)
                        await self.cpd_can_0.restbus.update_signals(
                            *[(restbus_signal, payload.get(ws_key)) for ws_key, restbus_signal in signal_map]
                        )
            except asyncio.CancelledError:
                logging.info("ws bridge camera_data_preprocessing cancelled, exiting loop")
                raise
            except Exception as exc:
                logging.warning(
                    "ws bridge camera_data_preprocessing error: %s — reconnecting in %.1fs",
                    exc, 2.0,
                )
                await asyncio.sleep(2.0)



async def main(avp: BehavioralModelArgs):
    logging.info("Starting DriverMonitoringECU simulator")

    async with BrokerClient(url=avp.url, auth=avp.auth) as broker_client:
        cpd_can_0 = CanNamespace(
            "DMS-CpdCan0",
            broker_client,
            restbus_configs=[RestbusConfig([filters.SenderFilter(ecu_name="DMS")], delay_multiplier=avp.delay_multiplier)],
        )

        drivermonitoringecu = DriverMonitoringECU(
            cpd_can_0=cpd_can_0,
        )

        async with BehavioralModel(
            "DMS",
            namespaces=[cpd_can_0],
            broker_client=broker_client,
            input_handlers=[
            ],
        ) as bm:
            drivermonitoringecu._start_ws_camera_data_preprocessing()
            try:
                await bm.run_forever()
            finally:
                drivermonitoringecu._stop_ws_camera_data_preprocessing()


if __name__ == "__main__":
    args = BehavioralModelArgs.parse()
    logging.basicConfig(level=args.loglevel)
    logging.getLogger("remotivelabs.topology").setLevel(logging.DEBUG)
    asyncio.run(main(args))
