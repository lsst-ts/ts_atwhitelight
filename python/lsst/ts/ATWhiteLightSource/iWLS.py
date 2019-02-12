import asyncio

import SALPY_ATWhiteLight
from lsst.ts import salobj
from lsst.ts.salobj import test_utils
from lsst.ts.ATWhiteLightSource.wlsCSC import WhiteLightSourceCSC
from collections import namedtuple

class iWLS(object):
    def __init__(self):
        self.csc = WhiteLightSourceCSC()
        self.csc.summary_state = salobj.State.ENABLED

        # set short cooldown and warmup periods so the tests don't take hours
        self.csc.model.cooldownPeriod = 3
        self.csc.model.warmupPeriod = 3

        self.remote = salobj.Remote(SALPY_ATWhiteLight, index=None)

    def slp(self, watts):
        """wraps the wattage number up in something that looks like id_data
            so these tests can easily call the csc do_setLightPower() method
        """
        dataclass = namedtuple('data', ['setLightPower'])
        id_dataclass = namedtuple('id_data', 'data')
        data = dataclass(watts)
        id_data = id_dataclass(data)
        return id_data

    def powerOn(self):
        async def doit():
            task = asyncio.ensure_future(self.csc.do_powerLightOn(None))
            await task
        asyncio.get_event_loop().run_until_complete(doit())

    def powerOff(self):
        async def doit():
            task = asyncio.ensure_future(self.csc.do_powerLightOff(None))
            await task
        asyncio.get_event_loop().run_until_complete(doit())

    def setPower(self, watts):
        async def doit():
            task = asyncio.ensure_future(self.csc.do_setLightPower(self.slp(watts)))
            await task
        asyncio.get_event_loop().run_until_complete(doit())