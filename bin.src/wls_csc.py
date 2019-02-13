#!/usr/bin/env python

import asyncio

from lsst.ts.ATWhiteLightSource.wlsCSC import WhiteLightSourceCSC
from lsst.ts.ATWhiteLightSource import version


csc = WhiteLightSourceCSC()
print("starting event loop...")
asyncio.get_event_loop().run_until_complete(csc.done_task)
