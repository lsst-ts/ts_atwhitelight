from .labjack_interface import LabJackInterface
from .lamp_base import LabJackChannels

class ATWhiteLightController:
    def __init__(self) -> None:
        pass

    @property
    def connected(self) -> tuple[bool, bool]:
        lamp_connected = (
            self.lamp_controller.connected & self.lamp_controller is not None
        )
        chiller_connected = (
            self.chiller_controller.connected & self.chiller_controller is not None
        )
        return lamp_connected, chiller_connected

    def connect_lamp(self) -> None:
        pass

    def connect_chiller(self) -> None:
        pass

    def disconnect_lamp(self) -> None:
        pass

    def disconnect_chiller(self) -> None:
        pass

    def start_chiller(self) -> None:
        pass

    def stop_chiller(self) -> None:
        pass

    def set_chiller_temperature(self) -> None:
        pass

    def start_lamp(self) -> None:
        pass

    def stop_lamp(self) -> None:
        pass

    def set_lamp_power(self) -> None:
        pass


class LampController:
    def __init__(self) -> None:
        self.client = None

    @property
    def connected(self):
        pass

    async def connect(self) -> None:
        if not self.connected:
            self.client = LabJackInterface()
            await self.client.connect()

    async def disconnect(self) -> None:
        await self.client.disconnect()
        self.client = None

    def set_power(self):
        await self.client.write(lamp_set_voltage=voltage)

    def turn_on(self):
        pass

    def turn_off(self):
        await self.client.write()

    def status_callback(self):
        pass


class ChillerController:
    def __init__(self) -> None:
        self.client = None

    @property
    def connected(self):
        pass

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def set_temperature(self) -> None:
        pass
