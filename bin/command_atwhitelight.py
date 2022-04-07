#!/usr/bin/env python

import asyncio
from lsst.ts import salobj


class ATWhiteLightCommander(salobj.CscCommander):
    def __init__(self, enable):
        super().__init__(
            name="ATWhiteLight",
            index=0,
            enable=enable,
            telemetry_fields_to_not_compare=("returnTemperature",),
        )


asyncio.run(ATWhiteLightCommander.amain(index=None))
