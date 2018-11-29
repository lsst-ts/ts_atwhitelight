import asyncio
import unittest

import SALPY_ATWhiteLight
from lsst.ts import salobj
from lsst.ts.ATWhiteLightSource.wlsCSC import WhiteLightSourceCSC


class WhiteLightSourcePowerOnTest(unittest.TestCase):
    def setUp(self):
        self.csc = WhiteLightSourceCSC()
        self.csc.summary_state = salobj.State.ENABLED

        self.remote = salobj.Remote(SALPY_ATWhiteLight, index=None)

    def testPowerOn(self):
        async def doit():
            self.assertEqual(self.csc.model.component.bulbState, 0)
            task = asyncio.ensure_future(self.csc.do_powerLightOn())
            await asyncio.sleep(0.3)
            self.assertEqual(self.csc.model.component.bulbState, 1200)
            await task
            self.assertEqual(self.csc.model.component.bulbState, 800)
        asyncio.get_event_loop().run_until_complete(doit())


if __name__ == "__main__":
    unittest.main()
