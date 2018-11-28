import salobj
import SALPY_WhiteLightSource #from salgenerator
import asyncio
from lsst.ts.ATWhiteLightSource.wlsModel import WhiteLightSourceModel
from salobj.base_csc import BaseCsc
from lsst.ts.statemachine.states import EnabledState, DefaultState, DisabledState, StandbyState, FaultState, OfflineState
from lsst.ts.statemachine.context import Context

class WhiteLightSourceCSC(BaseCsc):
    def __init__(inital_summary_state):
        super(SALPY_WhiteLightSource)
        self.model = WhiteLightSourceModel()
        self.summary_state = 
        

    async def do_powerLightOn(self):
        self.model.powerLightOn()

    async def do_powerLightOff(self):
        self.model.powerLightOff()

    async def do_setLightPower(self, watts):
        self.model.setLightPower(watts)

