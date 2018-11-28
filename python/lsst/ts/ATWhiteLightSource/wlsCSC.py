import salobj
import SALPY_WhiteLightSource #from salgenerator
import asyncio
from lsst.ts.ATWhiteLightSource.wlsModel import WhiteLightSourceModel
from salobj.base_csc import BaseCsc
import enum

class WLSDetailedStateEnum(enum.Enum):
    """ Enumeration of White Light Source substates

    Attributes
    ----------
        DISABLEDSTATE: int
        ENABLEDSTATE: int
        FAULTSTATE: int
        OFFLINESTATE: int
        STANDBYSTATE: int
        BULBLITSTATE: int
    """
    DISABLEDSTATE = 1
    ENABLEDSTATE = 2
    FAULTSTATE = 3
    OFFLINESTATE = 4
    STANDBYSTATE = 5
    BULBLITSTATE = 6


class WhiteLightSourceCSC(BaseCsc):
    def __init__(self, inital_summary_state):
        super(SALPY_WhiteLightSource)
        self.model = WhiteLightSourceModel()
#        self.summary_state = 

    def do_powerLightOn(self):
        self.model.powerLightOn()

    def do_powerLightOff(self):
        self.model.powerLightOff()

    def do_setLightPower(self, watts):
        self.model.setLightPower(watts)

