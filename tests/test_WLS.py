import asyncio
import unittest
import concurrent

import SALPY_ATWhiteLight
from lsst.ts import salobj
from lsst.ts.ATWhiteLightSource.wlsCSC import WhiteLightSourceCSC


class WhiteLightSourceCSCTests(unittest.TestCase):
    def setUp(self):
        self.csc = WhiteLightSourceCSC()
        self.csc.summary_state = salobj.State.ENABLED
        # change the bulb cooldown period to 3s instead of 5m to speed things up.
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

    def testPowerOff(self):
        """
        Tests the PowerLightOff command, which sets watts to 0.
        """
        async def doit():
            self.assertEqual(self.csc.model.component.bulbState, 0)
            task = asyncio.ensure_future(self.csc.do_powerLightOn())
            await task
            self.assertEqual(self.csc.model.component.bulbState, 800)
            task = asyncio.ensure_future(self.csc.do_powerLightOff())
            await task
            self.assertEqual(self.csc.model.component.bulbState, 0)
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

    def testCooldownPeriod(self):
        """
        Tests that when we power off, we're not allowed to power on during
        the cooldown period. Normally this is 5 minutes, but in this test
        it's 3 seconds.
        """
        async def doit():
            task = asyncio.ensure_future(self.csc.do_powerLightOn())
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

    def testCantPowerOffWhileOff(self):
        """
        Tests that we get an error when we try to turn off the bulb
        when it is already off.
        """
        async def doit():
            task = asyncio.ensure_future(self.csc.do_powerLightOn())
            await task
            task = asyncio.ensure_future(self.csc.do_powerLightOff())
            await task
            task = asyncio.ensure_future(self.csc.do_powerLightOff())
            with self.assertRaises(salobj.ExpectedError):
                await task

        asyncio.get_event_loop().run_until_complete(doit())

    def testPowerOffInterruptsPowerOn(self):
        """
        Tests if we signal a power-off during the initial ramp-up,
        the ramp-up is canceled and we go into cooldown mode.
        """
        async def doit():
            ontask = asyncio.ensure_future(self.csc.do_powerLightOn())
            await asyncio.sleep(0.3)
            self.assertEqual(self.csc.model.component.bulbState, 1200)
            offtask = asyncio.ensure_future(self.csc.do_powerLightOff())
            await offtask
            with self.assertRaises(concurrent.futures._base.CancelledError):
                await ontask
            self.assertEqual(self.csc.model.component.bulbState, 0)
        asyncio.get_event_loop().run_until_complete(doit())

    def testChangePowerDuringPowerOn(self):
        """
        Tests if we signal a wattage change during the initial ramp-up,
        the ramp-up is finishes and then we immediately go to the
        requested wattage.
        """
        async def doit():
            ontask = asyncio.ensure_future(self.csc.do_powerLightOn())
            await asyncio.sleep(0.3)
            self.assertEqual(self.csc.model.component.bulbState, 1200)
            changetask = asyncio.ensure_future(self.csc.do_setLightPower(1105))
            await ontask
            await changetask
            self.assertEqual(self.csc.model.component.bulbState, 1105)
        asyncio.get_event_loop().run_until_complete(doit())


if __name__ == "__main__":
    unittest.main()
