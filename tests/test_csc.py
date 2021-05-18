import pathlib
import asyncio
import unittest
from random import randrange
from lsst.ts import salobj
from lsst.ts import ATWhiteLightSource


STD_TIMEOUT = 15  # standard command timeout (sec)
TEST_CONFIG_DIR = pathlib.Path(__file__).parents[1].joinpath("tests", "data", "config")


class CscTestCase(salobj.BaseCscTestCase, unittest.IsolatedAsyncioTestCase):
    def basic_make_csc(self, initial_state, config_dir, simulation_mode):
        return ATWhiteLightSource.WhiteLightSourceCSC(
            initial_state=initial_state,
            config_dir=config_dir,
            simulation_mode=simulation_mode,
        )

    async def testBinScript(self):
        await self.check_bin_script("ATWhiteLight", 0, "run_ATWhiteLightSource.py")

    async def test_state_transitions(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.check_standard_state_transitions(
                enabled_commands=[
                    "powerLightOn",
                    "powerLightOff",
                    "emergencyPowerLightOff",
                    "setLightPower",
                    "setChillerTemperature",
                    "startCooling",
                    "stopCooling",
                ]
            )

    async def test_setChillerTemp(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            target_temp = randrange(18, 20)
            await self.remote.cmd_start.set_start(settingsToApply=None, timeout=20)
            self.csc.chillerModel.component.response_dict = {
                b".0103rSetTemp26\r": b"#01030rSetTemp+019040\r",
                b".0117sCtrlTmp+019025\r": b"#01170sCtrlTmp+01904A\r",
                b".0101WatchDog01\r": b"#01010WatchDog2101EA\r",
                b".0120rWarnLv1ee\r": b"#01200rWarnLv10800DB\r",
                b".0104rSupplyT46\r": b"#01040rSupplyT+02045C\r",
                b".0117sCtrlTmp+018024\r": b"#01170sCtrlTmp+018049\r",
            }
            await self.remote.cmd_enable.set_start(timeout=20)
            await self.remote.cmd_setChillerTemperature.set_start(
                temperature=target_temp, timeout=STD_TIMEOUT
            )
            await asyncio.sleep(6)
            self.assertEqual(self.csc.chillerModel.setTemp, target_temp)

    async def testPowerOn(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):

            await self.remote.cmd_start.set_start(settingsToApply=None, timeout=20)
            self.csc.chillerModel.component.response_dict = {
                b".0103rSetTemp26\r": b"#01030rSetTemp+019040\r",
                b".0115sStatus_17c\r": b"#01150sStatus_1A1\r",
                b".0101WatchDog01\r": b"#01010WatchDog2101EA\r",
                b".0120rWarnLv1ee\r": b"#01200rWarnLv10800DB\r",
                b".0104rSupplyT46\r": b"#01040rSupplyT+018867\r",
            }
            await self.remote.cmd_enable.set_start(timeout=STD_TIMEOUT)
            self.csc.kiloarcModel.warmupPeriod = 1
            await self.remote.cmd_startCooling.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(3)  # Sleep while we wait for chiller to start chilling.
            await self.remote.cmd_powerLightOn.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(0.3)  # Wait for light to start its 1200w startup burst.
            await asyncio.sleep(4)
            self.assertEqual(self.csc.kiloarcModel.component.bulbState, 800)

        await asyncio.sleep(10)

    async def testPowerOff(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.remote.cmd_start.set_start(settingsToApply=None, timeout=20)
            self.csc.chillerModel.component.response_dict = {
                b".0103rSetTemp26\r": b"#01030rSetTemp+019040\r",
                b".0115sStatus_17c\r": b"#01150sStatus_1A1\r",
                b".0101WatchDog01\r": b"#01010WatchDog2101EA\r",
                b".0120rWarnLv1ee\r": b"#01200rWarnLv10800DB\r",
                b".0104rSupplyT46\r": b"#01040rSupplyT+02065E\r",
                b".0107rReturnT3c\r": b"#01070rReturnT+012352\r",
                b".0108rAmbTemp0f\r": b"#01080rAmbTemp+02642B\r",
                b".0109rProsFlo2f\r": b"#01090rProsFlo+001949\r",
                b".0110rTECB1Cr66\r": b"#01100rTECB1Cr+002179\r",
                b".0111rTECDrLvb7\r": b"#01110rTECDrLv+0012CA\r",
                b".0113rTECB2Cr6a\r": b"#01130rTECB2Cr016,C95\r",
                b".0149rUpTime_21\r": b"#01490rUpTime_1654067C\r",
            }

            await self.remote.cmd_enable.set_start(timeout=STD_TIMEOUT)
            self.csc.kiloarcModel.cooldownPeriod = 15
            self.csc.kiloarcModel.warmupPeriod = 15
            await self.remote.cmd_startCooling.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(3)  # Sleep while we wait for chiller to start chilling.
            await self.remote.cmd_powerLightOn.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(5)
            self.assertEqual(self.csc.kiloarcModel.component.bulbState, 800)
            await self.csc.kiloarcModel.warmup_task
            await self.remote.cmd_powerLightOff.set_start(timeout=STD_TIMEOUT)
            self.assertEqual(self.csc.kiloarcModel.component.bulbState, 0)

    async def testSetPowerTooLow(self):
        """
        when we ask for 799 watts, we should treat that as 0
        """
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):

            await self.remote.cmd_start.set_start(settingsToApply=None, timeout=20)
            self.csc.chillerModel.component.response_dict = {
                b".0103rSetTemp26\r": b"#01030rSetTemp+01803F\r",
                b".0115sStatus_17c\r": b"#01150sStatus_1A1\r",
                b".0101WatchDog01\r": b"#01010WatchDog2101EA\r",
                b".0120rWarnLv1ee\r": b"#01200rWarnLv10800DB\r",
                b".0104rSupplyT46\r": b"#01040rSupplyT+017765\r",
                b".0107rReturnT3c\r": b"#01070rReturnT+012352\r",
                b".0108rAmbTemp0f\r": b"#01080rAmbTemp+02642B\r",
                b".0109rProsFlo2f\r": b"#01090rProsFlo+001949\r",
                b".0110rTECB1Cr66\r": b"#01100rTECB1Cr+00147B\r",
                b".0111rTECDrLvb7\r": b"#01110rTECDrLv+0070CE\r",
                b".0113rTECB2Cr6a\r": b"#01130rTECB2Cr052,C95\r",
                b".0149rUpTime_21\r": b"#01490rUpTime_1666427F\r",
            }
            await self.remote.cmd_enable.set_start(timeout=STD_TIMEOUT)
            self.csc.kiloarcModel.warmupPeriod = 15
            await self.remote.cmd_startCooling.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(3)  # Sleep while we wait for chiller to start chilling.
            await self.remote.cmd_powerLightOn.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(5)
            self.assertEqual(self.csc.kiloarcModel.component.bulbState, 800)
            await self.csc.kiloarcModel.warmup_task
            await self.remote.cmd_setLightPower.set_start(
                power=799, timeout=STD_TIMEOUT
            )
            await self.csc.kiloarcModel.warmup_task
            self.assertEqual(self.csc.kiloarcModel.component.bulbState, 0)

    async def testSetPowerTooHigh(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):

            await self.remote.cmd_start.set_start(settingsToApply=None, timeout=20)
            self.csc.chillerModel.component.response_dict = {
                b".0103rSetTemp26\r": b"#01030rSetTemp+01803F\r",
                b".0115sStatus_17c\r": b"#01150sStatus_1A1\r",
                b".0101WatchDog01\r": b"#01010WatchDog2101EA\r",
                b".0120rWarnLv1ee\r": b"#01200rWarnLv10800DB\r",
                b".0104rSupplyT46\r": b"#01040rSupplyT+017664\r",
                b".0107rReturnT3c\r": b"#01070rReturnT+012352\r",
                b".0108rAmbTemp0f\r": b"#01080rAmbTemp+026128\r",
                b".0109rProsFlo2f\r": b"#01090rProsFlo+001949\r",
                b".0110rTECB1Cr66\r": b"#01100rTECB1Cr+024581\r",
                b".0111rTECDrLvb7\r": b"#01110rTECDrLv+0219D3\r",
                b".0113rTECB2Cr6a\r": b"#01130rTECB2Cr059,C9C\r",
                b".0149rUpTime_21\r": b"#01490rUpTime_1681447E\r",
                b".0150rFanSpd1d3\r": b"#01500rFanSpd10000B8\r",
                b".0151rFanSpd2d5\r": b"#01510rFanSpd20000BA\r",
                b".0152rFanSpd3d7\r": b"#01520rFanSpd30000BC\r",
                b".0153rFanSpd4d9\r": b"#01530rFanSpd40000BE\r",
            }
            await self.remote.cmd_enable.set_start(timeout=STD_TIMEOUT)
            self.csc.kiloarcModel.warmupPeriod = 15
            await self.remote.cmd_startCooling.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(3)  # Sleep while we wait for chiller to start chilling.
            await self.remote.cmd_powerLightOn.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(5)
            self.assertEqual(self.csc.kiloarcModel.component.bulbState, 800)
            with salobj.assertRaisesAckError():  # (result_contains="too high"):
                await self.remote.cmd_setLightPower.set_start(
                    power=1201, timeout=STD_TIMEOUT
                )
            await self.csc.kiloarcModel.warmup_task
            await asyncio.sleep(10)

    async def testCantSetPowerWithBulbOff(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.remote.cmd_start.set_start(settingsToApply=None, timeout=20)
            self.csc.chillerModel.component.response_dict = {
                b".0103rSetTemp26\r": b"#01030rSetTemp+01803F\r",
                b".0115sStatus_17c\r": b"#01150sStatus_1A1\r",
                b".0101WatchDog01\r": b"#01010WatchDog2101EA\r",
                b".0120rWarnLv1ee\r": b"#01200rWarnLv10800DB\r",
                b".0104rSupplyT46\r": b"#01040rSupplyT+019464\r",
                b".0107rReturnT3c\r": b"#01070rReturnT+012352\r",
                b".0108rAmbTemp0f\r": b"#01080rAmbTemp+02632A\r",
                b".0109rProsFlo2f\r": b"#01090rProsFlo+001949\r",
                b".0110rTECB1Cr66\r": b"#01100rTECB1Cr+007784\r",
                b".0111rTECDrLvb7\r": b"#01110rTECDrLv+0066D3\r",
                b".0113rTECB2Cr6a\r": b"#01130rTECB2Cr047,C99\r",
            }
            await self.remote.cmd_enable.set_start(timeout=STD_TIMEOUT)
            self.csc.kiloarcModel.warmupPeriod = 15
            await self.remote.cmd_startCooling.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(3)  # Sleep while we wait for chiller to start chilling.
            with salobj.assertRaisesAckError():
                await self.remote.cmd_setLightPower.set_start(
                    power=1000, timeout=STD_TIMEOUT
                )
            await asyncio.sleep(10)

    async def testCantPowerOnDuringCooldownPeriod(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.remote.cmd_start.set_start(settingsToApply=None, timeout=20)
            self.csc.chillerModel.component.response_dict = {
                b".0103rSetTemp26\r": b"#01030rSetTemp+01803F\r",
                b".0115sStatus_17c\r": b"#01150sStatus_1A1\r",
                b".0101WatchDog01\r": b"#01010WatchDog2101EA\r",
                b".0120rWarnLv1ee\r": b"#01200rWarnLv10800DB\r",
                b".0104rSupplyT46\r": b"#01040rSupplyT+018665\r",
                b".0107rReturnT3c\r": b"#01070rReturnT+012352\r",
                b".0108rAmbTemp0f\r": b"#01080rAmbTemp+02632A\r",
                b".0109rProsFlo2f\r": b"#01090rProsFlo+001949\r",
                b".0110rTECB1Cr66\r": b"#01100rTECB1Cr+003982\r",
                b".0111rTECDrLvb7\r": b"#01110rTECDrLv+0049D4\r",
                b".0113rTECB2Cr6a\r": b"#01130rTECB2Cr041,C93\r",
                b".0149rUpTime_21\r": b"#01490rUpTime_1681417B\r",
                b".0150rFanSpd1d3\r": b"#01500rFanSpd10000B8\r",
                b".0151rFanSpd2d5\r": b"#01510rFanSpd20000BA\r",
                b".0152rFanSpd3d7\r": b"#01520rFanSpd30000BC\r",
                b".0153rFanSpd4d9\r": b"#01530rFanSpd40000BE\r",
            }

            await self.remote.cmd_enable.set_start(timeout=STD_TIMEOUT)
            self.csc.kiloarcModel.cooldownPeriod = 15
            self.csc.kiloarcModel.warmupPeriod = 15
            await self.remote.cmd_startCooling.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(3)  # Sleep while we wait for chiller to start chilling.
            await self.remote.cmd_powerLightOn.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(5)
            self.assertEqual(self.csc.kiloarcModel.component.bulbState, 800)
            await self.csc.kiloarcModel.warmup_task
            await self.remote.cmd_powerLightOff.set_start(timeout=STD_TIMEOUT)
            self.assertEqual(self.csc.kiloarcModel.component.bulbState, 0)
            with salobj.assertRaisesAckError():
                await self.remote.cmd_powerLightOn.set_start(timeout=STD_TIMEOUT)
            await self.csc.kiloarcModel.cooldown_task
            await self.remote.cmd_powerLightOn.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(10)

    async def testCantPowerOffDuringWarmupPeriod(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.remote.cmd_start.set_start(settingsToApply=None, timeout=20)
            self.assertIsNotNone(self.csc.kiloarcModel.component)
            self.csc.chillerModel.component.response_dict = {
                b".0103rSetTemp26\r": b"#01030rSetTemp+01803F\r",
                b".0115sStatus_17c\r": b"#01150sStatus_1A1\r",
                b".0101WatchDog01\r": b"#01010WatchDog2101EA\r",
                b".0120rWarnLv1ee\r": b"#01200rWarnLv10800DB\r",
                b".0104rSupplyT46\r": b"#01040rSupplyT+019565\r",
                b".0107rReturnT3c\r": b"#01070rReturnT+012352\r",
                b".0108rAmbTemp0f\r": b"#01080rAmbTemp+02632A\r",
                b".0109rProsFlo2f\r": b"#01090rProsFlo+001949\r",
                b".0110rTECB1Cr66\r": b"#01100rTECB1Cr+01507C\r",
                b".0111rTECDrLvb7\r": b"#01110rTECDrLv+0158D5\r",
                b".0113rTECB2Cr6a\r": b"#01130rTECB2Cr067,C9B\r",
                b".0149rUpTime_21\r": b"#01490rUpTime_16813982\r",
                b".0150rFanSpd1d3\r": b"#01500rFanSpd10000B8\r",
            }

            await self.remote.cmd_enable.set_start(timeout=STD_TIMEOUT)
            self.csc.kiloarcModel.cooldownPeriod = 15
            self.csc.kiloarcModel.warmupPeriod = 15
            await self.remote.cmd_startCooling.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(3)  # Sleep while we wait for chiller to start chilling.
            await self.remote.cmd_powerLightOn.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(5)
            self.assertEqual(self.csc.kiloarcModel.component.bulbState, 800)
            with salobj.assertRaisesAckError():
                await self.remote.cmd_powerLightOff.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(10)

    async def testEmergencyPowerLightOff(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.remote.cmd_start.set_start(settingsToApply=None, timeout=20)
            self.csc.chillerModel.component.response_dict = {
                b".0103rSetTemp26\r": b"#01030rSetTemp+01803F\r",
                b".0115sStatus_17c\r": b"#01150sStatus_1A1\r",
                b".0101WatchDog01\r": b"#01010WatchDog2101EA\r",
                b".0120rWarnLv1ee\r": b"#01200rWarnLv10800DB\r",
                b".0104rSupplyT46\r": b"#01040rSupplyT+018867\r",
                b".0107rReturnT3c\r": b"#01070rReturnT+012352\r",
                b".0108rAmbTemp0f\r": b"#01080rAmbTemp+026229\r",
                b".0109rProsFlo2f\r": b"#01090rProsFlo+001949\r",
                b".0110rTECB1Cr66\r": b"#01100rTECB1Cr+01617E\r",
                b".0111rTECDrLvb7\r": b"#01110rTECDrLv+0170CF\r",
                b".0113rTECB2Cr6a\r": b"#01130rTECB2Cr069,C9D\r",
                b".0149rUpTime_21\r": b"#01490rUpTime_1681427C\r",
                b".0150rFanSpd1d3\r": b"#01500rFanSpd10000B8\r",
                b".0151rFanSpd2d5\r": b"#01510rFanSpd20000BA\r",
            }
            await self.remote.cmd_enable.set_start(timeout=STD_TIMEOUT)
            self.csc.kiloarcModel.cooldownPeriod = 15
            self.csc.kiloarcModel.warmupPeriod = 15
            await self.remote.cmd_startCooling.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(3)  # Sleep while we wait for chiller to start chilling.
            await self.remote.cmd_powerLightOn.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(5)
            self.assertEqual(self.csc.kiloarcModel.component.bulbState, 800)
            await self.remote.cmd_emergencyPowerLightOff.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(10)

    async def testCantPowerOnBulbWithoutChiller(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):

            await self.remote.cmd_start.set_start(settingsToApply=None, timeout=20)
            self.csc.kiloarcModel.cooldownPeriod = 15
            self.csc.kiloarcModel.warmupPeriod = 15
            await self.remote.cmd_enable.set_start(timeout=STD_TIMEOUT)
            with salobj.assertRaisesAckError():
                await self.remote.cmd_powerLightOn.set_start(timeout=STD_TIMEOUT)

    async def testCantStopChillingWithBulbOn(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.remote.cmd_start.set_start(settingsToApply=None, timeout=20)
            self.csc.chillerModel.component.response_dict = {
                b".0103rSetTemp26\r": b"#01030rSetTemp+01803F\r",
                b".0115sStatus_17c\r": b"#01150sStatus_1A1\r",
                b".0101WatchDog01\r": b"#01010WatchDog2101EA\r",
                b".0120rWarnLv1ee\r": b"#01200rWarnLv10800DB\r",
                b".0104rSupplyT46\r": b"#01040rSupplyT+017866\r",
                b".0107rReturnT3c\r": b"#01070rReturnT+012352\r",
            }

            await self.remote.cmd_enable.set_start(timeout=STD_TIMEOUT)
            self.csc.kiloarcModel.cooldownPeriod = 15
            self.csc.kiloarcModel.warmupPeriod = 15
            await self.remote.cmd_startCooling.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(3)  # Sleep while we wait for chiller to start chilling.
            await self.remote.cmd_powerLightOn.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(5)
            self.assertEqual(self.csc.kiloarcModel.component.bulbState, 800)
            with salobj.assertRaisesAckError():
                await self.remote.cmd_stopCooling.set_start(timeout=STD_TIMEOUT)

    async def testBulbStopsWhenChillerDisconnected(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.remote.cmd_start.set_start(settingsToApply=None, timeout=20)
            self.csc.chillerModel.component.response_dict = {
                b".0103rSetTemp26\r": b"#01030rSetTemp+01803F\r",
                b".0115sStatus_17c\r": b"#01150sStatus_1A1\r",
                b".0101WatchDog01\r": b"#01010WatchDog2101EA\r",
                b".0120rWarnLv1ee\r": b"#01200rWarnLv10800DB\r",
                b".0104rSupplyT46\r": b"#01040rSupplyT+016764\r",
            }
            await self.remote.cmd_enable.set_start(timeout=STD_TIMEOUT)
            await self.remote.cmd_startCooling.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(3)  # Sleep while we wait for chiller to start chilling.
            await self.remote.cmd_powerLightOn.set_start(timeout=STD_TIMEOUT)
            await asyncio.sleep(0.3)  # Wait for light to start its 1200w startup burst.
            await asyncio.sleep(4)
            await self.csc.chillerModel.disconnect()
            await asyncio.sleep(5)
            self.assertEqual(self.csc.kiloarcModel.component.bulbState, 0)


if __name__ == "__main__":
    unittest.main()
