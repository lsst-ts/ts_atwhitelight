from lsst.ts.ATWhiteLightSource.chillerModel import ChillerModel
import unittest
import asyncio
import logging


class ModelTestCase(unittest.TestCase):
    def setup(self):
        pass

    def test_connect(self):
        self.cm = ChillerModel(logging.log(3, None))
        asyncio.get_event_loop().run_until_complete(self.cm.component.connect())
        print("connected?")
