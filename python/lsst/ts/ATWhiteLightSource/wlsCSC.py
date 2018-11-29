__all__ = ["WhiteLightSourceCSC"]

from lsst.ts import salobj
import SALPY_ATWhiteLight  # from salgenerator
from .wlsModel import WhiteLightSourceModel


class WhiteLightSourceCSC(salobj.BaseCsc):
    def __init__(self):
        super().__init__(SALPY_ATWhiteLight)
        self.model = WhiteLightSourceModel()

    async def do_powerLightOn(self):
        self.assert_enabled("powerLightOn")
        await self.model.powerLightOn()

    async def do_powerLightOff(self):
        await self.model.setLightPower(0)

    async def do_setLightPower(self, watts):
        self.assert_enabled("setLightPower")
        await self.model.setLightPower(watts)
