from wlsCSC import WhiteLightSourceCSC
import asyncio

async def TestPowerOn():
    csc = WhiteLightSourceCSC()
    await csc.do_powerLightOn()
    assert csc.model.component.bulbState == 800

async def TestPowerOff():
    model = WhiteLightSourceModel()
    await model.powerLightOn()
    await model.powerLightOff()
    assert model.component.bulbState == 0


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(TestPowerOn())
    asyncio.get_event_loop().run_until_complete(TestPowerOff())
