#!/usr/bin/env python

import asyncio
from lsst.ts.ATWhiteLightSource.wlsCSC import WhiteLightSourceCSC

asyncio.run(WhiteLightSourceCSC.amain(index=False))
