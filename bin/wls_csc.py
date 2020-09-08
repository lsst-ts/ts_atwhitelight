#!/usr/bin/env python

import asyncio

from lsst.ts.ATWhiteLightSource.wlsCSC import WhiteLightSourceCSC
from lsst.ts.ATWhiteLightSource import version

WhiteLightSourceCSC.amain(index=False)
