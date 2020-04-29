from lsst.ts.ATWhiteLightSource.chillerModel import ChillerModel
import unittest
import asyncio


class ModelTestCase(unittest.TestCase):

    def setup(self):
        self.cm = ChillerModel()
    
    def test_connect(self):
        asyncio.get_event_loop().run_until_complete(self.cm.component.connect())
        print("connected?")

    

