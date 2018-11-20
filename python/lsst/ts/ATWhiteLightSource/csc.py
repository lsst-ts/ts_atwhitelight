import salobj
import SALPY_WhiteLightSource #from salgenerator
import asyncio
from lsst.ts.ATWhiteLightSource.whiteLightSource import WhiteLightSourceComponent
from salobj.base_csc import BaseCsc

class WhiteLightSourceCSC(BaseCsc):
    def __init__(inital_summary_state):
        super(SALPY_WhiteLightSource)
        self.summary_state = 
        

    async def do_powerLightOn():
