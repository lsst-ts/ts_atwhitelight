import asyncio
import unittest

import asynctest

from lsst.ts import salobj
from lsst.ts import ATWhiteLightSource

STD_TIMEOUT = 2  # standard command timeout (sec)


class Harness:
    def __init__(self, initial_state, config_dir=None):
        self.csc = ATWhiteLightSource.WhiteLightSourceCSC(
            config_dir=config_dir,
            initial_state=initial_state,
            initial_simulation_mode=0)
        self.remote = salobj.Remote(domain=self.csc.domain, name="ATWhiteLight", index=0)
    
    async def __aenter__(self):
        await self.csc.start_task
        await self.remote.start_task
        return self

    async def __aexit__(self, *args):
        await self.remote.close()
        await self.csc.close()


class CscTestCase(asynctest.TestCase):
    def setUp(self):
        salobj.set_random_lsst_dds_domain()

    async def test_initial_info(self):
        async with Harness(initial_state=salobj.State.ENABLED) as harness:
            state = await harness.remote.evt_summaryState.next(flush=False, timeout=STD_TIMEOUT)
            self.assertEqual(state.summaryState, salobj.State.ENABLED)

    async def test_setChillerTemp(self):
        async with Harness(initial_state=salobj.State.ENABLED) as harness:
            await harness.remote.cmd_setChillerTemperature.set_start(temperature=20.0, timeout=STD_TIMEOUT)


if __name__ == "__main__":
    unittest.main()