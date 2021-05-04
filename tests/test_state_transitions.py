import asynctest
import asyncio
import pathlib

import asynctest

from lsst.ts import salobj
from lsst.ts import ATWhiteLightSource


STD_TIMEOUT = 15  # standard command timeout (sec)
TEST_CONFIG_DIR = pathlib.Path(__file__).parents[1].joinpath("tests", "data", "config")


class CscTestCase(salobj.BaseCscTestCase, asynctest.TestCase):
    def basic_make_csc(self, initial_state, config_dir, simulation_mode):
        return ATWhiteLightSource.WhiteLightSourceCSC(
            initial_state=initial_state,
            config_dir=config_dir,
            simulation_mode=simulation_mode,
        )

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