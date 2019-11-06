import asyncio
import unittest

import asynctest

from lsst.ts import salobj
from lsst.ts import ATWhiteLightSource
from random import randrange

STD_TIMEOUT = 5  # standard command timeout (sec)


class Harness:
    def __init__(self, initial_state, config_dir=None):
        salobj.set_random_lsst_dds_domain()
        self.csc = ATWhiteLightSource.WhiteLightSourceCSC(
            config_dir=config_dir,
            initial_state=initial_state,
            initial_simulation_mode=1)
        self.remote = salobj.Remote(domain=self.csc.domain, name="ATWhiteLight", index=0)
    
    async def __aenter__(self):
        await self.csc.start_task
        await self.remote.start_task
        return self

    async def __aexit__(self, *args):
        await self.remote.close()
        await self.csc.close()


class CscTestCase(asynctest.TestCase):
    async def test_initial_info(self):
        async with Harness(initial_state=salobj.State.ENABLED) as harness:
            state = await harness.remote.evt_summaryState.next(flush=False, timeout=STD_TIMEOUT)
            self.assertEqual(state.summaryState, salobj.State.ENABLED)


    async def test_setChillerTemp(self):
        async with Harness(initial_state=salobj.State.STANDBY) as harness:
            target_temp = randrange(18,20)
            harness.csc.chillerModel.component.response_dict = {
                b'.0103rSetTemp26\r': b'#01030rSetTemp+019040\r', 
                b'.0117sCtrlTmp+019025\r': b'#01170sCtrlTmp+01904A\r', 
                b'.0101WatchDog01\r': b'#01010WatchDog2101EA\r', 
                b'.0120rWarnLv1ee\r': b'#01200rWarnLv10800DB\r', 
                b'.0104rSupplyT46\r': b'#01040rSupplyT+02045C\r', 
                b'.0117sCtrlTmp+018024\r': b'#01170sCtrlTmp+018049\r'}
            await harness.remote.cmd_start.set_start(settingsToApply=None, timeout=STD_TIMEOUT)
            await harness.remote.cmd_setChillerTemperature.set_start(temperature=target_temp, timeout=STD_TIMEOUT)
            await asyncio.sleep(5)
            self.assertEqual(harness.csc.chillerModel.setTemp, target_temp)
            print("setChillerTemp")
            print(harness.csc.chillerModel.component.response_dict) 

    async def testPowerOn(self):
        async with Harness(initial_state=salobj.State.STANDBY) as harness:
            harness.csc.kiloarcModel.warmupPeriod = 1
            harness.csc.chillerModel.component.response_dict = {
                b'.0103rSetTemp26\r': b'#01030rSetTemp+019040\r', 
                b'.0115sStatus_17c\r': b'#01150sStatus_1A1\r', 
                b'.0101WatchDog01\r': b'#01010WatchDog2101EA\r', 
                b'.0120rWarnLv1ee\r': b'#01200rWarnLv10800DB\r', 
                b'.0104rSupplyT46\r': b'#01040rSupplyT+018867\r'}
            await harness.remote.cmd_start.set_start(settingsToApply=None, timeout=STD_TIMEOUT)
            await harness.remote.cmd_enable.set_start(timeout=STD_TIMEOUT)
            await harness.remote.cmd_startCooling.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(3) # Sleep while we wait for chiller to start chilling. 
            await harness.remote.cmd_powerLightOn.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(0.3) # Wait for light to start its 1200w startup burst. 
            await asyncio.sleep(4)
            self.assertEqual(harness.csc.kiloarcModel.component.bulbState, 800)
        
        await asyncio.sleep(10)

    async def testPowerOff(self):
        async with Harness(initial_state=salobj.State.STANDBY) as harness:
            harness.csc.chillerModel.component.response_dict = {
                b'.0103rSetTemp26\r': b'#01030rSetTemp+019040\r',
                b'.0115sStatus_17c\r': b'#01150sStatus_1A1\r',
                b'.0101WatchDog01\r': b'#01010WatchDog2101EA\r',
                b'.0120rWarnLv1ee\r': b'#01200rWarnLv10800DB\r', 
                b'.0104rSupplyT46\r': b'#01040rSupplyT+02065E\r', 
                b'.0107rReturnT3c\r': b'#01070rReturnT+012352\r', 
                b'.0108rAmbTemp0f\r': b'#01080rAmbTemp+02642B\r', 
                b'.0109rProsFlo2f\r': b'#01090rProsFlo+001949\r', 
                b'.0110rTECB1Cr66\r': b'#01100rTECB1Cr+002179\r', 
                b'.0111rTECDrLvb7\r': b'#01110rTECDrLv+0012CA\r', 
                b'.0113rTECB2Cr6a\r': b'#01130rTECB2Cr016,C95\r', 
                b'.0149rUpTime_21\r': b'#01490rUpTime_1654067C\r'
            }
            harness.csc.kiloarcModel.cooldownPeriod = 15
            harness.csc.kiloarcModel.warmupPeriod = 15
            await harness.remote.cmd_start.set_start(settingsToApply=None, timeout=STD_TIMEOUT)
            await harness.remote.cmd_enable.set_start(timeout=STD_TIMEOUT)
            await harness.remote.cmd_startCooling.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(3) # Sleep while we wait for chiller to start chilling. 
            await harness.remote.cmd_powerLightOn.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(5)
            self.assertEqual(harness.csc.kiloarcModel.component.bulbState, 800)
            await harness.csc.kiloarcModel.warmup_task
            await harness.remote.cmd_powerLightOff.set_start(timeout=STD_TIMEOUT)
            self.assertEqual(harness.csc.kiloarcModel.component.bulbState, 0)

    async def testSetPowerTooLow(self):
        """
        when we ask for 799 watts, we should treat that as 0
        """
        async with Harness(initial_state=salobj.State.STANDBY) as harness:
            harness.csc.kiloarcModel.warmupPeriod = 15
            harness.csc.chillerModel.component.response_dict = {
            b'.0103rSetTemp26\r': b'#01030rSetTemp+01803F\r', 
            b'.0115sStatus_17c\r': b'#01150sStatus_1A1\r', 
            b'.0101WatchDog01\r': b'#01010WatchDog2101EA\r', 
            b'.0120rWarnLv1ee\r': b'#01200rWarnLv10800DB\r', 
            b'.0104rSupplyT46\r': b'#01040rSupplyT+017765\r', 
            b'.0107rReturnT3c\r': b'#01070rReturnT+012352\r', 
            b'.0108rAmbTemp0f\r': b'#01080rAmbTemp+02642B\r', 
            b'.0109rProsFlo2f\r': b'#01090rProsFlo+001949\r', 
            b'.0110rTECB1Cr66\r': b'#01100rTECB1Cr+00147B\r', 
            b'.0111rTECDrLvb7\r': b'#01110rTECDrLv+0070CE\r', 
            b'.0113rTECB2Cr6a\r': b'#01130rTECB2Cr052,C95\r', 
            b'.0149rUpTime_21\r': b'#01490rUpTime_1666427F\r'}

            await harness.remote.cmd_start.set_start(settingsToApply=None, timeout=STD_TIMEOUT)
            await harness.remote.cmd_enable.set_start(timeout=STD_TIMEOUT)
            await harness.remote.cmd_startCooling.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(3) # Sleep while we wait for chiller to start chilling. 
            await harness.remote.cmd_powerLightOn.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(5)
            self.assertEqual(harness.csc.kiloarcModel.component.bulbState, 800)
            await harness.csc.kiloarcModel.warmup_task
            await harness.remote.cmd_setLightPower.set_start(power=799, timeout=STD_TIMEOUT)
            await harness.csc.kiloarcModel.warmup_task
            self.assertEqual(harness.csc.kiloarcModel.component.bulbState, 0)



if __name__ == "__main__":
    unittest.main()