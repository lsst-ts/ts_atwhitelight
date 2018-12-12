__all__ = ["WhiteLightSourceCSC"]

from lsst.ts import salobj
import SALPY_ATWhiteLight  # from salgenerator
from .wlsModel import WhiteLightSourceModel
import asyncio
import time


class WhiteLightSourceCSC(salobj.BaseCsc):
    def __init__(self):
        super().__init__(SALPY_ATWhiteLight)
        self.model = WhiteLightSourceModel()
        
        #topic objects
        self.bulb_uptime_topic = self.tel_bulbHours.DataType()
        self.bulb_uptime_watthours_topic = self.tel_bulbWattHours.DataType()
        self.status_event_topic = self.evt_whiteLightStatus.DataType()

        self.uptime_telemetry_publish_interval = 5

        #start the event and telemetry
        asyncio.ensure_future(self.sendTelemetry())
        asyncio.ensure_future(self.eventListenerLoop())

    async def do_powerLightOn(self):
        self.assert_enabled("powerLightOn")
        await self.model.powerLightOn()

    async def do_powerLightOff(self):
        await self.model.setLightPower(0)

    async def do_setLightPower(self, watts):
        self.assert_enabled("setLightPower")
        await self.model.setLightPower(watts)
    
    async def do_emergencyPowerLightOff(self):
        await self.model.emergencyPowerLightOff()
    
    async def do_setLogLevel(self):
        pass


    async def eventListenerLoop(self):
        """ Periodically checks with the component to see if the wattage
            or the hardware's "status light" has changed. If so, we publish
            an event
        """
        previousState = self.model.component.checkStatus()
        while True:
            currentState = self.model.component.checkStatus()
            if currentState != previousState:
                #something has changed, so publish a new status event
                self.status_event_topic.wattageChange = float(currentState[0])
                self.status_event_topic.coolingDown = currentState[2]
                self.status_event_topic.acceptingCommands = currentState[1]
                self.status_event_topic.error = currentState[4]

                self.evt_whiteLightStatus.put(self.status_event_topic)
            await asyncio.sleep(1)



    async def sendTelemetry(self):
        """ Publish WLS Telemetry. This includes:
                bulb uptime (hours)
                bulb uptime (watt-hours)

            Parameters
            ----------
            None

            Returns
            -------
            None
        """

        while True:
            #calculate uptime and wattage since the last iteration of this loop
            lastIntervalUptime = time.time() - self.model.component.bulbHoursLastUpdate
            lastIntervalWattHours = lastIntervalUptime * self.model.component.bulbState

            #if the bulb is on, update the tracking variables in the component
            if self.model.bulb_on:
                self.model.component.bulbHours += lastIntervalUptime
                self.model.component.bulbWattHours += lastIntervalWattHours
            
            #update time of last update
            self.model.component.bulbHoursLastUpdate = time.time()

            #update topics with latest data from component
            self.bulb_uptime_topic.bulbHours = float(self.model.component.bulbHours)
            self.bulb_uptime_watthours_topic.bulbHours = float(self.model.component.bulbWattHours)
            
            #publish the topics to sal
            self.tel_bulbHours.put(self.bulb_uptime_topic)
            self.tel_bulbWattHours.put(self.bulb_uptime_watthours_topic)

            await asyncio.sleep(self.uptime_telemetry_publish_interval)

