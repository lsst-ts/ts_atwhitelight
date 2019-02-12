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

        # topic objects
        self.bulb_uptime_topic = self.tel_bulbHours.DataType()
        self.bulb_uptime_watthours_topic = self.tel_bulbWattHours.DataType()
        self.status_event_topic = self.evt_whiteLightStatus.DataType()

        self.telemetry_publish_interval = 5
        self.event_listener_interval = 1

        # start the event and telemetry loopd
        asyncio.ensure_future(self.sendTelemetry())
        asyncio.ensure_future(self.eventListenerLoop())

    async def do_powerLightOn(self, id_data):
        self.assert_enabled("powerLightOn")
        await self.model.powerLightOn()

    async def do_powerLightOff(self, id_data):
        await self.model.setLightPower(0)

    async def do_setLightPower(self, id_data):
        self.assert_enabled("setLightPower")
        await self.model.setLightPower(id_data.data.setLightPower)

    async def do_emergencyPowerLightOff(self, id_data):
        await self.model.emergencyPowerLightOff()

    async def do_setLogLevel(self, id_data):
        pass

    async def eventListenerLoop(self):
        """ Periodically checks with the component to see if the wattage
            and/or the hardware's "status light" has changed. If so, we 
            publish an event
        """
        previousState = self.model.component.checkStatus()
        while True:
            currentState = self.model.component.checkStatus()
            if currentState != previousState:
                # something has changed, so publish a new status event
                #self.status_event_topic.wattageChange = float(currentState[0]) #old way
                #self.evt_statusEvent.data.wattageChange =float(currentState[0]) #new way
                #self.status_event_topic.coolingDown = currentState[2]
                #self.status_event_topic.acceptingCommands = currentState[1]
                #self.status_event_topic.error = currentState[4]

                self.evt_whiteLightStatus.set_put(
                    wattageChange = float(currentState[0]),
                    coolingDown = currentState[2],
                    acceptingCommands = currentState[1],
                    error = currentState[4],
                )

                self.evt_whiteLightStatus.put(self.status_event_topic)
                previousState = currentState
            await asyncio.sleep(self.event_listener_interval)

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
            # calculate uptime and wattage since the last iteration of this loop
            lastIntervalUptime = time.time()/3600 - self.model.component.bulbHoursLastUpdate
            lastIntervalWattHours = lastIntervalUptime * self.model.component.bulbState

            # if the bulb is on, update the tracking variables in the component
            if self.model.bulb_on:
                self.model.component.bulbHours += lastIntervalUptime
                self.model.component.bulbWattHours += lastIntervalWattHours

            # set time of last update to current time
            self.model.component.bulbHoursLastUpdate = time.time()/3600

            # update topics with latest data from component
            self.bulb_uptime_topic.bulbHours = float(self.model.component.bulbHours)
            self.bulb_uptime_watthours_topic.bulbHours = float(self.model.component.bulbWattHours)

            # publish the topics to sal
            self.tel_bulbHours.put(self.bulb_uptime_topic)
            self.tel_bulbWattHours.put(self.bulb_uptime_watthours_topic)

            await asyncio.sleep(self.telemetry_publish_interval)