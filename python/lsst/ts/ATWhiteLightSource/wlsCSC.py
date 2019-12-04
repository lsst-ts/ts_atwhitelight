__all__ = ["WhiteLightSourceCSC"]

from lsst.ts import salobj
from .wlsModel import WhiteLightSourceModel
from .chillerModel import ChillerModel
import pathlib
import asyncio
import time
import enum
from pymodbus.exceptions import ConnectionException


class WLSDetailedState(enum.IntEnum):
    """ For the White Light Source, detailed state is implemented
        as a representation of the state of the KiloArc hardware,
        based on its reported status. As such, there are four 
        possible detailed states:

        OFFLINE:    We are receiving no signal from the KiloArc;
                    the status LED is not illuminated.
        READY:      The KiloArc bulb is either illuminated, or it 
                    is ready to be illuminated. Status LED is
                    green.
        COOLDOWN:   The bulb is off, and KiloArc's internal fans 
                    are active. Status LED is blue. This state 
                    lasts for 5m, and is independent of the 15m 
                    software-enforced cooldown and warmup periods.
        ERROR:      KiloArc is reporting an error. Status LED is 
                    red. This always sends the CSC into a FAULT
                    state. 
        DISCONNECTED:We are unable to determine the state of the
                    KiloArc because we have lost our connection
                    to the ADAM device. 
    """
    OFFLINE = 1
    READY = 2
    COOLDOWN = 3
    ERROR = 4
    DISCONNECTED = 5

class WhiteLightSourceCSC(salobj.ConfigurableCsc):
    """ 
    The White Light Source CSC class

    Parameters
    ----------
    sim_mode : int
        0 to init the CSC to control the actual hardware
        1 to init the CSC in simulation mode
    
    Attributes
    ----------
    model : WhiteLightSourceModel
        the model representing the white light hardware
    detailed_state : WLSDetailedStateEnum
        represents the reported state of the Kiloarc
    telemetry_publish_interval: int/float
        frequency, in seconds, that we publish telemetry
    hardware_listener_interval : int/float
        frequency, in seconds, that we check in on the hardware
    """
    def __init__(self, config_dir=None, initial_state=salobj.State.STANDBY, initial_simulation_mode=0):
        schema_path = pathlib.Path(__file__).resolve().parents[4].joinpath("schema", "whitelight.yaml")
        super().__init__("ATWhiteLight", index=0, schema_path=schema_path, config_dir=config_dir,
                         initial_state=initial_state, initial_simulation_mode=initial_simulation_mode)
        self.kiloarcModel = None
        
        self.detailed_state = WLSDetailedState.OFFLINE

        self.telemetry_publish_interval = 5
        self.hardware_listener_interval = 2
        self.chillerModel = ChillerModel()
        self.kiloarcModel = WhiteLightSourceModel()
        self.sim_mode = 0

        #setup asyncio tasks for the loops
        done_task = asyncio.Future()
        done_task.set_result(None)
        self.telemetryLoopTask = done_task
        self.kiloarcListenerTask = done_task


        self.keep_on_chillin_task = done_task
        self.lamp_off_time = None

        self.config = None
        self.kiloarc_com_lock = asyncio.Lock()

        self.kilo_interloc = asyncio.ensure_future(self.kiloarc_interlock_loop())

        self.interlockLoopBool = True
        self.telemetryLoopBool = True
        self.kiloarcListenerLoopBool = True

        self.last_warning_state = None


    @staticmethod
    def get_config_pkg():
        return("ts_config_atcalsys")

    async def configure(self, config):
        print('csc config')
        self.config = config
        self.chillerModel.config = config
        self.kiloarcModel.config = config
        

    async def begin_standby(self, id_data):
        """ When we leave fault state to enter standby, we 
            need to make sure that the hardware isn't still
            reporting errors
        """
        print("begin_standby()")
        # don't let the user leave fault state if the KiloArc
        # or chiller is reporting an error
        if self.summary_state == salobj.State.FAULT:
            async with self.kiloarc_com_lock:
                if self.kiloarcModel.component.checkStatus().redLED:
                    raise RuntimeError("Can't enter Standby state while KiloArc still reporting errors")
        if self.chillerModel.alarmPresent:
            raise RuntimeError("Can't enter Standby state while chiller is still reporting alarm status")
        if not self.keep_on_chillin_task.done():
            remaining = round(self.config.keep_on_chillin_timer - (time.time() - self.lamp_off_time), 0)
            raise RuntimeError(f"Can't enter Standby state; chiller must stay on for {self.config.keep_on_chillin_timer} seconds. {remaining} seconds remain.")
        
        self.telemetryLoopTask.cancel()
        self.kiloarcListenerTask.cancel()
        await self.chillerModel.disconnect()
        self.kiloarcModel.disconnect()
        
        

    async def begin_enable(self, id_data):
        """ Upon entering ENABLE state, we need to start 
            the telemetry and hardware listener loops.
        """
        print("begin_enable()")
        

    async def begin_start(self, id_data):
        """ Executes during the STANDBY --> DISABLED state
            transition. Confusing name, IMHO. 
        """
        print("begin_start()")
        await super().begin_start(id_data)
        self.kiloarcModel.connect()
        self.telemetryLoopTask = asyncio.ensure_future(self.telemetryLoop())
        self.kiloarcListenerTask = asyncio.ensure_future(self.kiloarcListenerLoop())
        await asyncio.wait_for(self.chillerModel.connect(self.config.chiller_ip, self.config.chiller_port), timeout=5)
        await self.apply_warnings_and_alarms()
        print("done with start")

    async def begin_disable(self, id_data):
        print("begin_disable()")

    async def end_standby(self, id_data):
        print("end_standby()")
        await self.chillerModel.disconnect()

    async def implement_simulation_mode(self, sim_mode):
        """ Swaps between real and simulated component upon request.
        """
        self.sim_mode = sim_mode
        self.kiloarcModel.simulation_mode = sim_mode


    async def apply_warnings_and_alarms(self):
        await self.chillerModel.apply_warnings_and_alarms(self.config)

    async def do_powerLightOn(self, id_data):
        """ Powers the light on. It will go to 1200 watts, then drop
            back down to 800. Not available of the lamp is still
            cooling down.
        """
        self.assert_enabled("powerLightOn")
        # make sure the chiller is running, and not reporting any alarms
        await self.chillerModel.priority_watchdog()
        if self.chillerModel.chillerStatus != 1:
            raise salobj.ExpectedError("Can't power light on unless chiller is running.")
        if self.chillerModel.alarmPresent == 1:  # TODO make this pass along the specific alarm
            raise salobj.ExpectedError("Can't power light on while chiller is reporting an Alarm")
        await self.kiloarcModel.powerLightOn()

    async def do_powerLightOff(self, id_data):
        """ Powers the light off. Not available of the lamp is still 
            warming up.
        """
        await self.kiloarcModel.setLightPower(0)
        self.lamp_off_time = time.time()
        self.keep_on_chillin_task = asyncio.ensure_future(self.keep_on_chillin())

    async def keep_on_chillin(self):
        await asyncio.sleep(self.config.keep_on_chillin_timer)
        if self.summary_state == salobj.State.FAULT:
            # if we're in fault, automatically stop the chiller once it's safe to do so.
            await self.do_stopCooling()
        await asyncio.sleep(5)


    async def do_setLightPower(self, id_data):
        """ Sets the light power. id_data must contain a topic that 
            specifies the wattage, between 800 and 1200. Numbers 
            below 800 will be treated like a powerLightOff command.
        """
        self.assert_enabled("setLightPower")
        await self.kiloarcModel.setLightPower(id_data.power)

    async def do_emergencyPowerLightOff(self, id_data):
        """ Powers the light off. This one ignores the warmup period
            that the CSC normally enforces.
        """
        await self.kiloarcModel.emergencyPowerLightOff()
        self.lamp_off_time = time.time()
        self.keep_on_chillin_task = asyncio.ensure_future(self.keep_on_chillin())

    async def do_setChillerTemperature(self,id_data):
        """ Sets the target temperature for the chiller

                Parameters
                ----------
                temperature : float

                Returns
                -------
                None
        """
        t = id_data.temperature
        if t > self.config.chiller_high_supply_temp_warning:
            raise salobj.ExpectedError(f"The temperature you have set is above the safe range limit of {self.config.chiller_high_supply_temp_warning}. To change this, edit the chiller_high_supply_temp_warning value in config")
        elif t < self.config.chiller_low_supply_temp_warning:
            raise salobj.ExpectedError(f"The temperature you have set is below the safe range limit of {self.config.chiller_low_supply_temp_warning}. To change this, edit the chiller_high_supply_temp_warning value in config")
        await self.chillerModel.setControlTemp(id_data.temperature)
        

    async def do_startCooling(self,id_data):
        """ Powers chiller on

                Parameters
                ----------
                None

                Returns
                -------
                None
            """
        self.assert_enabled("startCooling")
        await self.chillerModel.startChillin()

    async def do_stopCooling(self,id_data):
        """ powers chiller off. Not available when bulb is on. 

                Parameters
                ----------
                None

                Returns
                -------
                None
            """
        if self.kiloarcModel.component is not None:
            if not self.kiloarcModel.component.client.connect():
                raise salobj.ExpectedError("Can't stop chillin' when we're disconnected from the Kiloarc's ADAM; we don't know if the lamp is still running and in need of cooling.")
        if self.kiloarcModel.bulb_on:
            raise salobj.ExpectedError("Can't stop chillin' while the bulb is still on, or bulb state is unknown.")
        if not self.keep_on_chillin_task.done():
            remaining = round(self.config.keep_on_chillin_timer - (time.time() - self.lamp_off_time),0) + 5
            raise salobj.ExpectedError(f"Lamp was recently extinguished; can't stop chillin' for {remaining} seconds.")
        else:
            await self.chillerModel.stopChillin()

    async def kiloarc_interlock_loop(self):
        """
        Make sure we stop the bulb if something bad happens with the chiller
        """
        while self.interlockLoopBool:
            print(self.summary_state)
            if self.kiloarcModel.bulb_on:
                if self.chillerModel.alarmPresent:
                    print("**Alarm Present")
                    self.fault(report="Alarm description")
                    await self.kiloarcModel.emergencyPowerLightOff()
                if self.chillerModel.chillerStatus != 1:
                    self.summary_state = salobj.State.FAULT
                    print("**Chiller Status not RUN")
                    await self.kiloarcModel.emergencyPowerLightOff()
                if self.chillerModel.pumpStatus == 0:
                    self.summary_state = salobj.State.FAULT
                    print("**Chiller Pump OFF ")
                    await self.kiloarcModel.emergencyPowerLightOff()
                if self.chillerModel.reconnect_failed:
                    self.summary_state = salobj.State.FAULT
                    print("**Chiller disconnected")
                    await self.kiloarcModel.emergencyPowerLightOff()

            await asyncio.sleep(1)



    async def reconnect_kiloarc_or_fault(self, max_attempts=3):
        async with self.kiloarc_com_lock:
            self.log.debug("Attempting reconnect to kiloarc")
            num_attempts = 0
            while num_attempts < max_attempts:
                num_attempts += 1 
                self.log.debug("iteration "+ str(num_attempts))
                try:
                    self.log.debug("trying reconnect...")
                    self.kiloarcModel.component.reconnect()
                    self.kiloarcModel.component.checkStatus()  # this triggers the exception we're fishing for.
                    self.log.debug("it worked")
                    break
                except ConnectionException:
                    self.log.debug("kiloarc connection problem, attempting reconnect " + str(num_attempts))
                    self.log.debug(str(num_attempts) + " " + str(max_attempts))
                    if num_attempts >= max_attempts:
                        self.log.debug("going FAULT")
                        self.summary_state = salobj.State.FAULT
                        self.detailed_state = WLSDetailedState.DISCONNECTED
                        self.telemetryLoopTask.cancel()
                        self.kiloarcListenerTask.cancel() #TODO do we really want to stop this one?
                
                await asyncio.sleep(1.5)

    async def kiloarcListenerLoop(self):
        """ Periodically checks with the component to see if the wattage
            and/or the hardware's "status light" has changed. If so, we
            publish an event to SAL. Unlike the LEDs, the wattage isn't
            *actually* read from the hardware; we only know what wattage
            the CSC is requesting.
        """
        # if we can't connect to the ADAM, stop loops and go to FAULT state
        # and DISCONNECTED detailed state.
        previousState = None
        try:
            async with self.kiloarc_com_lock:
                previousState = self.kiloarcModel.component.checkStatus()
        except ConnectionException:
            await self.reconnect_kiloarc_or_fault()
        
        while self.kiloarcListenerLoopBool:
            #if we lose connection to the ADAM, stop loops and go to FAULT state
            try:
                async with self.kiloarc_com_lock:
                    currentState = self.kiloarcModel.component.checkStatus()
                    print(currentState)
                if currentState != previousState:
                    self.evt_whiteLightStatus.set_put(
                        wattageChange = float(currentState.wattage),
                        coolingDown = currentState.blueLED,
                        acceptingCommands = currentState.greenLED,
                        error = currentState.redLED,
                    )
                # update detailed state
                if currentState.greenLED:
                    self.detailed_state = WLSDetailedState.READY
                elif currentState.blueLED:
                    self.detailed_state = WLSDetailedState.COOLDOWN
                elif currentState.redLED:
                    self.detailed_state = WLSDetailedState.ERROR
                else:
                    self.detailed_state = WLSDetailedState.OFFLINE
                previousState = currentState
            except Exception as e:
                print(e)
                print("Connection Problem with ADAM/KIloarc")
                await self.reconnect_kiloarc_or_fault()

            # if the KiloArc error light is on, put the CSC into FAULT state
            if currentState.redLED:
                try:
                    if self.kiloarcModel.bulb_on:
                        await self.kiloarcModel.emergencyPowerLightOff()
                except salobj.ExpectedError as e:
                    print("Attempted emergency shutoff of light, but got error: "+ str(e))
                print("kiloarc reporting error FAULT")
                self.summary_state = salobj.State.FAULT
                self.lamp_off_time = time.time()
                self.keep_on_chillin_task = asyncio.ensure_future(self.keep_on_chillin())
                self.detailed_state = WLSDetailedState.ERROR
            await asyncio.sleep(self.hardware_listener_interval)
        print("Kiloarc listener loop OVER")

    async def telemetryLoop(self):
        """ Publish WLS Telemetry. This includes:
                bulb uptime (hours)
                bulb uptime (watt-hours)
                Chiller fan speed, coolant temperature

            Parameters
            ----------
            None

            Returns
            -------
            None
        """
        self.last_warning_state = {}
        while self.telemetryLoopBool:
            # Kiloarc Telemetry

            # calculate uptime and wattage since the last iteration of this loop
            lastIntervalUptime = time.time()/3600 - self.kiloarcModel.component.bulbHoursLastUpdate
            lastIntervalWattHours = lastIntervalUptime * self.kiloarcModel.component.bulbState

            # if the bulb is on, update the tracking variables in the component
            if self.kiloarcModel.bulb_on:
                self.kiloarcModel.component.bulbHours += lastIntervalUptime
                self.kiloarcModel.component.bulbWattHours += lastIntervalWattHours

            # set time of last update to current time
            self.kiloarcModel.component.bulbHoursLastUpdate = time.time()/3600

            # publish telemetry
            self.tel_bulbhour.set_put(bulbhour=float(self.kiloarcModel.component.bulbHours))
            self.tel_bulbWatthour.set_put(bulbhour=float(self.kiloarcModel.component.bulbWattHours))

            # Chiller Telemetry
            print(str(self.chillerModel))
            self.tel_chillerFansSpeed.set(fan1Speed=int(self.chillerModel.fan1speed))
            self.tel_chillerFansSpeed.set(fan2Speed=int(self.chillerModel.fan2speed))
            self.tel_chillerFansSpeed.set(fan3Speed=int(self.chillerModel.fan3speed))
            self.tel_chillerFansSpeed.set(fan4Speed=int(self.chillerModel.fan4speed))
            self.tel_chillerFansSpeed.set(timestamp=time.time())
            self.tel_chillerFansSpeed.put()

            if self.chillerModel.chillerUptime is not None:
                self.tel_chillerUpTime.set(upTime=self.chillerModel.chillerUptime)
            self.tel_chillerUpTime.set(timestamp=time.time())
            self.tel_chillerUpTime.put()
            
            if self.chillerModel.setTemp is not None:
                self.tel_chillerTempSensors.set(setTemperature=self.chillerModel.setTemp)
            if self.chillerModel.supplyTemp is not None:
                self.tel_chillerTempSensors.set(supplyTemperature=self.chillerModel.supplyTemp)
            if self.chillerModel.returnTemp is not None:
                self.tel_chillerTempSensors.set(returnTemperature=self.chillerModel.returnTemp)
            if self.chillerModel.ambientTemp is not None:
                self.tel_chillerTempSensors.set(ambientTemperature=self.chillerModel.ambientTemp)
            self.tel_chillerTempSensors.set(timestamp=time.time())
            self.tel_chillerTempSensors.put()

            if self.chillerModel.processFlow is not None:
                self.tel_chillerProcessFlow.set(flow=self.chillerModel.processFlow)
            self.tel_chillerProcessFlow.set(timestamp=time.time())
            self.tel_chillerProcessFlow.put()
            
            if self.chillerModel.tecBank1 is not None:
                self.tel_chillerTECBankCurrent.set(bank1Current=self.chillerModel.tecBank1)
            if self.chillerModel.tecBank2 is not None:
                self.tel_chillerTECBankCurrent.set(bank2Current=self.chillerModel.tecBank2)
            self.tel_chillerTECBankCurrent.set(timestamp=time.time())
            self.tel_chillerTECBankCurrent.put()

            if self.chillerModel.teDrivePct is not None:
                self.tel_chillerTEDriveLevel.set(chillerTEDriveLevel=self.chillerModel.teDrivePct)
            self.tel_chillerTEDriveLevel.set(timestamp=time.time())
            self.tel_chillerTEDriveLevel.put()

            # Chiller Events
            if "Low Process Flow Warning" in self.chillerModel.warnings:
                self.evt_chillerLowFlowWarning.set_put(timestamp=time.time(), warning=True)
                self.last_warning_state["Low Process Flow Warning"] = True
            elif "Low Process Flow Warning" in self.last_warning_state and self.last_warning_state["Low Process Flow Warning"]:
                self.evt_chillerLowFlowWarning.set_put(timestamp=time.time(), warning=False)
                self.last_warning_state["Low Process Flow Warning"] = False

            if "Process Fluid Level Warning" in self.chillerModel.warnings:
                self.evt_chillerFluidLevelWarning.set_put(timestamp=time.time(), warning=True)
                self.last_warning_state["Process Fluid Level Warning"] = True
            elif "Process Fluid Level Warning" in self.last_warning_state and self.last_warning_state["Process Fluid Level Warning"]:
                self.evt_chillerFluidLevelWarning.set_put(timestamp=time.time(), warning=False)
                self.last_warning_state["Process Fluid Level Warning"] = False

            if "Switch to Supply Temp as Control Temp Warning" in self.chillerModel.warnings:
                self.evt_chillerSwitchToSupplyTempWarning.set_put(timestamp=time.time(), warning=True)
                self.last_warning_state["Switch to Supply Temp as Control Temp Warning"] = True
            elif "Switch to Supply Temp as Control Temp Warning" in self.last_warning_state and self.last_warning_state["Switch to Supply Temp as Control Temp Warning"]:
                self.evt_chillerSwitchToSupplyTempWarning.set_put(timestamp=time.time(), warning=False)
                self.last_warning_state["Switch to Supply Temp as Control Temp Warning"] = False

            if "High Control Temp Warning" in self.chillerModel.warnings:
                self.evt_chillerHighControlTempWarning.set_put(timestamp=time.time(), warning=True)
                self.last_warning_state["High Control Temp Warning"] = True
            elif "High Control Temp Warning" in self.last_warning_state and self.last_warning_state["High Control Temp Warning"]:
                self.evt_cchillerHighControlTempWarning.set_put(timestamp=time.time(), warning=False)
                self.last_warning_state["High Control Temp Warning"] = False

            if "Low Control Temp Warning" in self.chillerModel.warnings:
                self.evt_chillerLowControlTempWarning.set_put(timestamp=time.time(), warning=True)
                self.last_warning_state["Low Control Temp Warning"] = True
            elif "Low Control Temp Warning" in self.last_warning_state and self.last_warning_state["Low Control Temp Warning"]:
                self.evt_chillerLowControlTempWarning.set_put(timestamp=time.time(), warning=False)
                self.last_warning_state["Low Control Temp Warning"] = False

            if "High Ambient Temp Warning" in self.chillerModel.warnings:
                self.evt_chillerHighAmbientTempWarning.set_put(timestamp=time.time(), warning=True)
                self.last_warning_state["High Ambient Temp Warning"] = True
            elif "High Ambient Temp Warning" in self.last_warning_state and self.last_warning_state["High Ambient Temp Warning"]:
                self.evt_cchillerHighAmbientTempWarning.set_put(timestamp=time.time(), warning=False)
                self.last_warning_state["High Ambient Temp Warning"] = False

            if "Low Ambient Temp Warning" in self.chillerModel.warnings:
                self.evt_chillerLowAmbientTempWarning.set_put(timestamp=time.time(), warning=True)
                self.last_warning_state["Low Ambient Temp Warning"] = True
            elif "Low Ambient Temp Warning" in self.last_warning_state and self.last_warning_state["Low Ambient Temp Warning"]:
                self.evt_chillerLowAmbientTempWarning.set_put(timestamp=time.time(), warning=False)
                self.last_warning_state["Low Ambient Temp Warning"] = False

            await asyncio.sleep(self.telemetry_publish_interval)
        print("Telemetry loop OVER")

    async def close(self):
        print("Running CLOSE")
        
        self.interlockLoopBool = False
        self.telemetryLoopBool = False
        self.kiloarcListenerLoopBool = False
        self.kiloarcModel.disconnect()
        await self.chillerModel.disconnect()
        await self.kilo_interloc
        await self.telemetryLoopTask
        await self.kiloarcListenerTask
        self.kiloarcModel.cooldown_task.cancel()
        self.kiloarcModel.warmup_task.cancel()
        await super().close()


