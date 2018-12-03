import asyncio
import unittest

import SALPY_ATWhiteLight
from lsst.ts import salobj
from lsst.ts.ATWhiteLightSource.wlsCSC import WhiteLightSourceCSC


class WhiteLightSourcePowerOnTest(unittest.TestCase):
    def setUp(self):
        self.csc = WhiteLightSourceCSC()
        self.csc.summary_state = salobj.State.ENABLED
        # change the bulb cooldownperiod to 3s instead of 5m to speed up the test.
        self.csc.model.cooldownPeriod = 3

        self.remote = salobj.Remote(SALPY_ATWhiteLight, index=None)

    def testPowerOn(self):
        """
        Tests bulb wattage ramps to 1200 for 2 sec, then drops to 800.
        """
        async def doit():
            self.assertEqual(self.csc.model.component.bulbState, 0)
            task = asyncio.ensure_future(self.csc.do_powerLightOn())
            await asyncio.sleep(0.3)
            self.assertEqual(self.csc.model.component.bulbState, 1200)
            await task
            self.assertEqual(self.csc.model.component.bulbState, 800)
        asyncio.get_event_loop().run_until_complete(doit())

    def testSetPower(self):
        """
        Tests bulb wattage setting.
        """
        async def doit():
            task = asyncio.ensure_future(self.csc.do_powerLightOn())
            await task
            self.assertEqual(self.csc.model.component.bulbState, 800)

            # set to 950 watts
            task = asyncio.ensure_future(self.csc.do_setLightPower(950))
            await task
            self.assertEqual(self.csc.model.component.bulbState, 950)

            # any setting below 800 should result in 0 watts
            task = asyncio.ensure_future(self.csc.do_setLightPower(799))
            await task
            self.assertEqual(self.csc.model.component.bulbState, 0)
        asyncio.get_event_loop().run_until_complete(doit())

    def testSetPowerTooLow(self):
        """
        Tests that we power off when we request a wattage <800.
        """
        async def doit():
            task = asyncio.ensure_future(self.csc.do_powerLightOn())
            await task
            self.assertEqual(self.csc.model.component.bulbState, 800)

            # any setting below 800 should result in 0 watts
            task = asyncio.ensure_future(self.csc.do_setLightPower(799))
            await task
            self.assertEqual(self.csc.model.component.bulbState, 0)
        asyncio.get_event_loop().run_until_complete(doit())

    def testSetPowerTooHigh(self):
        """
        Make sure we get an exception when we set the wattage too high.
        """
        async def doit():
            task = asyncio.ensure_future(self.csc.do_powerLightOn())
            await task

            # any setting over 1200 should produce an exception
            task = asyncio.ensure_future(self.csc.do_setLightPower(1201))
            with self.assertRaises(salobj.ExpectedError):
                await task
        asyncio.get_event_loop().run_until_complete(doit())

    def testCooloffPeriod(self):
        """
        Tests that when we power off, we're not allowed to power on for 5m.
        """
        async def doit():
            self.assertEqual(self.csc.model.component.bulbState, 0)
            task = asyncio.ensure_future(self.csc.do_powerLightOn())
            await asyncio.sleep(0.3)
            self.assertEqual(self.csc.model.component.bulbState, 1200)
            await task
            self.assertEqual(self.csc.model.component.bulbState, 800)

            offtask = asyncio.ensure_future(self.csc.do_powerLightOff())
            await asyncio.sleep(0.5)
            ontask = asyncio.ensure_future(self.csc.do_powerLightOn())
            with self.assertRaises(salobj.ExpectedError):
                await ontask
            await offtask
            await asyncio.sleep(3)
            ontask2 = asyncio.ensure_future(self.csc.do_powerLightOn())
            await ontask2
            self.assertEqual(self.csc.model.component.bulbState, 800)
        asyncio.get_event_loop().run_until_complete(doit())


if __name__ == "__main__":
    unittest.main()
