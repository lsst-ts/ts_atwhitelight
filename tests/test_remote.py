import asyncio
import unittest

import SALPY_ATWhiteLight
from lsst.ts import salobj
from lsst.ts.ATWhiteLightSource.wlsCSC import WhiteLightSourceCSC


class WhiteLightSourceCSCTests(unittest.TestCase):
    def setUp(self):
        self.csc = WhiteLightSourceCSC()
        self.csc.summary_state = salobj.State.ENABLED

        # set short cooldown and warmup periods so the tests don't take hours
        self.csc.model.cooldownPeriod = 3
        self.csc.model.warmupPeriod = 3

        self.remote = salobj.Remote(SALPY_ATWhiteLight, index=None)

    def testPowerOn(self):
        """
        Tests we can power on through the Remote system.
        """
        async def doit():
            timeout = 5

            powerOn_topic = self.remote.cmd_powerLightOn.DataType()
            powerOn_topic.power = True
            powerOn_ack = await self.remote.cmd_powerLightOn.start(powerOn_topic, timeout)

            powerOff_topic = self.remote.cmd_powerLightOff.DataType()
            powerOff_topic.power = False
            powerOff_ack = await self.remote.cmd_powerLightOff.start(powerOff_topic, timeout)
        asyncio.get_event_loop().run_until_complete(doit())


if __name__ == "__main__":
    unittest.main()
