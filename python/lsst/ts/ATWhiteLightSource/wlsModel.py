from lsst.ts.ATWhiteLightSource.wlsComponent import WhiteLightSourceComponent
from lsst.ts.ATWhiteLightSource.wlsSimComponent import WhiteLightSourceComponentSimulator
import wlsExceptions
import time
import asyncio

class WhiteLightSourceModel():

    def __init__(self):
        #self.component = WhiteLightSourceComponent()
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
        if not self.off_task.done(): # are we in the cooldown period?
            elapsed = time.time() - self.off_time
            remaining = 300 - elapsed
            raise salobj.ExpectedException("Can't power on bulb during cool-off period. Please wait " + str(remaining) + " seconds.")
        self.component.setLightPower(self.startupWattage)
        self.bulb_on = True
        self.on_task = asyncio.ensure_future(asyncio.sleep(self.startupTime))
        await self.on_task
        self.component.setLightPower(self.defaultWattage)
        
    
    def powerLightOff(self):
        
        if not self.on_task.done():
            self.on_task.cancel()
        self.component.setLightPower(0)
    
    def setLightPower(self, watts):
        """ Sets the brightness (in watts) on the white light source.
            We always set the brightness to self.startupWattage for a
            moment (self.startupTime), then step it back down to the 
            target wattage.

            Parameters
            ----------
            watts : int or float
                Should be in the range of 800-1200 (inclusive)

            Returns
            -------
            None
        """
        # TODO: report watts as telemetry
        if watts > 1200: 
            raise salobj.ExpectedException(f"Wattage {watts} too high (over 1200)")
        if watts < 800:
            # turn bulb off
            if not self.on_task.done(): 
                # if we're in the middle of powering on, cancel that task. 
                self.on_task.cancel()
            if self.bulb_on:
                self.off_task = asyncio.ensure_future(asyncio.sleep(300))
                self.component.setLightPower(0)
                self.bulb_on = False
                self.off_time = time.time()
        else:
            if self.bulb_on == False: 
                raise salobj.ExpectedException("Bulb is already off")
            await self.on_task
            self.component.setLightPower(watts)
            self.bulb_on = True
