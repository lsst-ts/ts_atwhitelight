from lsst.ts import salobj
import SALPY_WhiteLightSource #from salgenerator
from lsst.ts.ATWhiteLightSource.wlsModel import WhiteLightSourceModel


class WhiteLightSourceCSC(salobj.BaseCsc):
    def __init__(self):
        super(SALPY_WhiteLightSource)
        self.model = WhiteLightSourceModel()

    def do_powerLightOn(self):
        self.assert_enabled("powerLightOn")
        self.model.powerLightOn()

    def do_powerLightOff(self):
        self.model.powerLightOff()

    def do_setLightPower(self, watts):
        self.assert_enabled("setLightPower")
        self.model.setLightPower(watts)

