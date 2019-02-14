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
        #self.status_event_topic = self.evt_whiteLightStatus.DataType()

        self.telemetry_publish_interval = 5
        self.event_listener_interval = 1

        # start the event and telemetry loops
        asyncio.ensure_future(self.sendTelemetry())
        asyncio.ensure_future(self.eventListenerLoop())

    async def implement_simulation_mode(self, sim_mode):
        """ Swaps between real and simulated component upon request.
            Should not be called while CSC is running
        """
        print("sim mode " + str(sim_mode))
        if sim_mode == 0: 
            self.model.component = self.model.realComponent # TODO: change this to realComponent
        else: self.model.component = self.model.simComponent

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
            publish an event to SAL.
        """
        previousState = self.model.component.checkStatus()
        while True:
            currentState = self.model.component.checkStatus()
            if currentState != previousState:
                print("Voltage change detected! \nError status: " + str(currentState))
                

                self.evt_whiteLightStatus.set_put(
                    wattageChange = float(currentState.wattage),
                    coolingDown = currentState.blueLED,
                    acceptingCommands = currentState.greenLED,
                    error = currentState.redLED,
                )

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