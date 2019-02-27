__all__ = ["WhiteLightSourceCSC"]

from lsst.ts import salobj
import SALPY_ATWhiteLight
from .wlsModel import WhiteLightSourceModel
import asyncio
import time


class WhiteLightSourceCSC(salobj.BaseCsc):
    def __init__(self):
        super().__init__(SALPY_ATWhiteLight)
        self.model = WhiteLightSourceModel()

        self.telemetry_publish_interval = 5
        self.hardware_listener_interval = 2

        #setup asyncio tasks for the loops
        done_task = asyncio.Future()
        done_task.set_result(None)
        self.telemetryLoopTask = done_task
        self.hardwareListenerTask = done_task

        asyncio.ensure_future(self.stateloop())

    
        

    def begin_standby(self,id_data):
        # don't let the user leave fault state if the KiloArc
        # is reporting an error
        if self.summary_state == salobj.State.FAULT:
            if self.model.component.checkStatus().redLED: #TODO change this to redLED
                raise RuntimeError("Can't enter Standby state while KiloArc still reporting errors")


    def begin_enable(self, id_data):
        """ Upon entering ENABLE state, we need to start 
            the telemetry and hardware listener loops.
        """
        print("begin_enable()")
        self.telemetryLoopTask = asyncio.ensure_future(self.telemetryLoop())
        self.hardwareListenerTask = asyncio.ensure_future(self.hardwareListenerLoop())

    def begin_start(self, id_data):
        """ Executes during the STANDBY --> DISABLED state
            transition. Confusing name, IMO. 
        """
        print("begin_start()")
        self.telemetryLoopTask.cancel()
        self.hardwareListenerTask.cancel()
        
    def begin_disable(self, id_data):
        print("begin_disable()")
        self.telemetryLoopTask.cancel()
        self.hardwareListenerTask.cancel()
        

    async def implement_simulation_mode(self, sim_mode):
        """ Swaps between real and simulated component upon request.
        """
        print("sim mode " + str(sim_mode))
        if sim_mode == 0: 
            self.model.component = self.model.realComponent
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

    async def stateloop(self):
        while True:
            print("current state: "+str(self.summary_state))
            print("HW listener task: " + str(self.hardwareListenerTask))
            await asyncio.sleep(1)


    async def hardwareListenerLoop(self):
        """ Periodically checks with the component to see if the wattage
            and/or the hardware's "status light" has changed. If so, we
            publish an event to SAL. Unlike the LEDs, the wattage isn't
            *actually* read from the hardware; we only know what wattage
            the CSC is requesting.
        """
        previousState = self.model.component.checkStatus()
        while True:
            currentState = self.model.component.checkStatus()
            if currentState != previousState:
                print("Voltage change detected! \n" + str(currentState))
                self.evt_whiteLightStatus.set_put(
                    wattageChange = float(currentState.wattage),
                    coolingDown = currentState.blueLED,
                    acceptingCommands = currentState.greenLED,
                    error = currentState.redLED,
                )
            previousState = currentState

            #if the KiloArc error light is on, put the CSC into FAULT state   
            if currentState.redLED:
                try:
                    if self.model.bulb_on:
                        await self.model.emergencyPowerLightOff()
                except salobj.ExpectedError as e:
                    print("Attempted emergency shutoff of light, but got error: "+ str(e))
                self.summary_state = salobj.State.FAULT

            print("HW Loop running")
            await asyncio.sleep(self.hardware_listener_interval)

    async def telemetryLoop(self):
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

            # publish telemetry
            self.tel_bulbHours.set_put(bulbHours = float(self.model.component.bulbHours))
            self.tel_bulbWattHours.set_put(bulbHours = float(self.model.component.bulbWattHours))
            print("Telemetry Loop Running")
            await asyncio.sleep(self.telemetry_publish_interval)