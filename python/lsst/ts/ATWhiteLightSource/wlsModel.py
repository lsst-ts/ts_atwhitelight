__all__ = ["WhiteLightSourceModel"]

import time
import asyncio

# from .wlsComponent import WhiteLightSourceComponent
from .wlsSimComponent import WhiteLightSourceComponentSimulator
from lsst.ts import salobj


class WhiteLightSourceModel():

    def __init__(self):
        # self.component = WhiteLightSourceComponent()
        self.component = WhiteLightSourceComponentSimulator()
        self.startupWattage = 1200
        self.defaultWattage = 800
        self.startupTime = 2
        done_task = asyncio.Future()
        done_task.set_result(None)
        self.on_task = done_task
        self.off_task = done_task
        self.bulb_on = False
        self.off_time = None
        self.cooldownPeriod = 300

    async def powerLightOn(self):
        """ Signals the Horiba device to power light on.
            We always set the brightness to self.startupWattage for a
            moment (self.startupTime), then step it back down to the
            default.

            Parameters
            ----------
            None

            Returns
            -------
            None
        """
        if not self.off_task.done():  # are we in the cooldown period?
            elapsed = time.time() - self.off_time
            remaining = self.cooldownPeriod - elapsed
            description = "Can't power on bulb during cool-off period. Please wait "
            raise salobj.ExpectedError(description + str(remaining) + " seconds.")
        self.component.setLightPower(self.startupWattage)
        self.bulb_on = True
        self.on_task = asyncio.ensure_future(asyncio.sleep(self.startupTime))
        await self.on_task
        self.component.setLightPower(self.defaultWattage)

    async def setLightPower(self, watts):
        """ Sets the brightness (in watts) on the white light source.

            Parameters
            ----------
            watts : int or float
                Should be <= 1200. Values under 800 power the light off entirely.

            Returns
            -------
            None
        """
        # TODO: report watts as telemetry (or events?)
        if watts > 1200:
            raise salobj.ExpectedError(f"Wattage {watts} too high (over 1200)")
        if watts < 800:
            # turn bulb off
            if not self.on_task.done():
                # if we're in the middle of powering on, cancel that task.
                self.on_task.cancel()
            if self.bulb_on:
                self.off_task = asyncio.ensure_future(asyncio.sleep(self.cooldownPeriod))
                self.component.setLightPower(0)
                self.bulb_on = False
                self.off_time = time.time()
            else:
                raise salobj.ExpectedError("Bulb is already off")
        else:
            # this executes when watts are inside the 800-1200 range
            if not self.on_task.done():
                await self.on_task
                self.component.setLightPower(watts)
                self.bulb_on = True
            else:
                self.component.setLightPower(watts)
                self.bulb_on = True
