#!/usr/bin/env python

import asyncio
from lsst.ts.atwhitelight import ATWhiteLightCsc

asyncio.run(ATWhiteLightCsc.amain(index=False))
