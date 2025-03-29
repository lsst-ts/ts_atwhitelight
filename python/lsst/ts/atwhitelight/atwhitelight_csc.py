# This file is part of ts_atwhitelight.
#
# Developed for the Vera C. Rubin Observatory Telescope and Site Systems.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__all__ = ["ATWhiteLightCsc", "ErrorCode", "run_atwhitelight"]

import asyncio
import copy
import enum
import types

from lsst.ts import salobj
from lsst.ts.xml.enums.ATWhiteLight import (
    ChillerControllerState,
    LampBasicState,
    LampControllerError,
    LampControllerState,
    ShutterState,
)

from . import __version__
from .chiller_model import ChillerModel
from .config_schema import CONFIG_SCHEMA
from .lamp_model import ONOFF_COMMAND_TIMEOUT_MARGIN, LampModel


class ErrorCode(enum.IntEnum):
    """CSC fault state error codes."""

    CHILLER_DISCONNECTED = 1
    LAMP_DISCONNECTED = 2
    LAMP_ERROR = 3
    CHILLER_ERROR = 4
    NOT_CHILLING_WITH_LAMP_ON = 5
    LAMP_UNEXPECTEDLY_OFF = 6
    LAMP_UNEXPECTEDLY_ON = 7


class ATWhiteLightCsc(salobj.ConfigurableCsc):
    """White light controller for the auxiliary telescope.

    Parameters
    ----------
    config_dir : `str`, optional
        Directory of configuration files, or None for the standard
        configuration directory (obtained from `_get_default_config_dir`).
        This is provided for unit testing.
    initial_state : `State` or `int`, optional
        The initial state of the CSC. This is provided for unit testing,
        as real CSCs should start up in `State.STANDBY`, the default.
    override : `str`, optional
        Configuration override file to apply if ``initial_state`` is
        `State.DISABLED` or `State.ENABLED`.
    simulation_mode : `int`, optional
        Simulation mode; one of:

        * 0 for normal operation
        * 1 for simulation

    Attributes
    ----------
    lamp_model : `LampModel`
        The model representing the white light lamp controller.
    chiller_model: `ChillerModel`
        The model representing the chiller.
    """

    version = __version__
    valid_simulation_modes = (0, 1)

    def __init__(
        self,
        config_dir=None,
        initial_state=salobj.State.STANDBY,
        override="",
        simulation_mode=0,
    ):
        self.lamp_model = None
        self.chiller_model = None

        # Unit tests can set either or both of these true to make
        # the connect method time out in the appropriate model.
        # Ignored unless in simulation mode.
        self.chiller_make_connect_time_out = False
        self.lamp_make_connect_time_out = False

        # Set True just after the lamp and chiller are both connected,
        # and false just before disconnecting them.
        self.should_be_connected = False

        # Time at which the lamp went on or off (TAI, unix seconds).
        # Used by the lamp model for cooldown and warmup timers.
        # Saved here so we can preserve the data when disconnected.
        self.lamp_on_time = 0
        self.lamp_off_time = 0

        self.config = None

        super().__init__(
            name="ATWhiteLight",
            index=0,
            config_schema=CONFIG_SCHEMA,
            config_dir=config_dir,
            initial_state=initial_state,
            override=override,
            simulation_mode=simulation_mode,
        )

    @staticmethod
    def get_config_pkg():
        return "ts_config_atcalsys"

    @property
    def chiller_connected(self):
        """Return True if the chiller is connected and configured."""
        return self.chiller_model is not None and self.chiller_model.configured

    @property
    def lamp_connected(self):
        """Return True if the LabJack is connected and has seen status."""
        return self.lamp_model is not None and self.lamp_model.status_seen

    async def configure(self, config):
        config = copy.copy(config)
        config.chiller = types.SimpleNamespace(**config.chiller)
        config.lamp = types.SimpleNamespace(**config.lamp)
        if (
            config.chiller.initial_temperature
            < config.chiller.low_supply_temperature_warning
        ):
            raise salobj.ExpectedError(
                f"config.chiller.initial_temperature={config.chiller.initial_temperature} "
                f"< low_supply_temperature_warning={config.chiller.low_supply_temperature_warning}"
            )
        if (
            config.chiller.initial_temperature
            > config.chiller.high_supply_temperature_warning
        ):
            raise salobj.ExpectedError(
                f"config.chiller.initial_temperature={config.chiller.initial_temperature} "
                f"> high_supply_temperature_warning={config.chiller.high_supply_temperature_warning}"
            )
        self.config = config

    async def handle_summary_state(self):
        if self.disabled_or_enabled:
            if not self.chiller_connected:
                try:
                    await self.connect_chiller()
                except Exception as e:
                    return await self.fault(
                        code=ErrorCode.CHILLER_ERROR,
                        report=f"Could not connect to the chiller: {e!r}",
                    )
            if self.summary_state == salobj.State.ENABLED:
                chiller_watchdog = self.chiller_model.get_watchdog()
                if chiller_watchdog.alarmsPresent:
                    return await self.fault(
                        code=ErrorCode.CHILLER_ERROR,
                        report="Chiller is reporting alarms",
                    )
            if not self.lamp_connected:
                try:
                    await self.connect_lamp()
                except Exception as e:
                    return await self.fault(
                        code=ErrorCode.LAMP_ERROR,
                        report=f"Could not connect to the lamp: {e!r}",
                    )
            self.should_be_connected = True
        elif self.summary_state == salobj.State.FAULT:
            if self.lamp_model and self.lamp_model.lamp_was_on:
                # Turn off the lamp, if connected
                if self.lamp_connected:
                    self.log.warning(
                        "Going to fault while connected to the lamp controller; "
                        "trying to turn the lamp off immediately."
                    )
                    try:
                        await self.lamp_model.turn_lamp_off(
                            force=True, wait=False, reason="CSC is going to FAULT state"
                        )
                    except Exception as e:
                        self.log.error(
                            f"Failed to turn lamp off; please turn it off manually: {e!r}"
                        )
                else:
                    self.log.warning(
                        "Going to fault and not connect to the lamp controller; "
                        "please turn the lamp off manually."
                    )
        else:
            self.should_be_connected = False
            if self.lamp_connected and self.lamp_model.lamp_was_on:
                try:
                    await self.lamp_model.turn_lamp_off(
                        force=True,
                        wait=False,
                        reason=f"CSC is going to state {self.summary_state!r}",
                    )
                except Exception as e:
                    self.log.warning(
                        f"Going to state {self.summary_state!r} but failed to turn off lamp: {e!r}; "
                        "please turn it off manually."
                    )
            await self.disconnect_lamp()
            await self.disconnect_chiller()

    async def connect_chiller(self):
        """Connect to the chiller, configure it and get status.

        Raises
        ------
        asyncio.TimeoutError
            If it takes longer than self.config.chiller.connect_timeout
        """
        await self.disconnect_chiller()
        if self.chiller_model is None:
            self.chiller_model = ChillerModel(
                config=self.config.chiller,
                csc=self,
                log=self.log,
                status_callback=self.status_callback,
                simulate=self.simulation_mode != 0,
                make_connect_time_out=self.chiller_make_connect_time_out,
            )
        await asyncio.wait_for(
            self.chiller_model.connect(), timeout=self.config.chiller.connect_timeout
        )

    async def connect_lamp(self):
        """Connect to the lamp controller LabJack and get status.

        Raises
        ------
        asyncio.TimeoutError
            If it takes longer than self.config.lamp.connect_timeout
        """
        await self.disconnect_lamp()
        if self.lamp_model is None:
            self.lamp_model = LampModel(
                config=self.config.lamp,
                csc=self,
                log=self.log,
                status_callback=self.status_callback,
                simulate=self.simulation_mode != 0,
                make_connect_time_out=self.lamp_make_connect_time_out,
            )
        await asyncio.wait_for(
            self.lamp_model.connect(), timeout=self.config.lamp.connect_timeout
        )

    async def disconnect_chiller(self):
        try:
            # Don't use chiller_connected because that can be false
            # even if a basic connection exists (before status seen)
            if self.chiller_model is None:
                return
            await self.chiller_model.disconnect()
            # Delete the chiller model because the config may change.
            self.chiller_model = None
        except Exception as e:
            self.log.warning(f"Failed to disconnect chiller; continuing: {e!r}")

    async def disconnect_lamp(self):
        try:
            # Don't use self.lamp_connected because that can be false
            # even if a basic connection exists (before status seen)
            if self.lamp_model is None:
                return
            await self.lamp_model.disconnect()
            # Delete the lamp model because the config may change.
            self.lamp_model = None
        except Exception as e:
            self.log.warning(f"Failed to disconnect lamp; continuing: {e!r}")

    async def begin_standby(self, data):
        """Make sure the hardware is not reporting errors"""
        # don't let the user leave fault state if the KiloArc
        # or chiller is reporting an error
        if self.summary_state == salobj.State.FAULT:
            if self.lamp_connected:
                lamp_state = self.lamp_model.get_state()
                if lamp_state.controllerError != LampControllerError.NONE:
                    raise salobj.ExpectedError(
                        f"Lamp controller error code={lamp_state.controllerError!r}"
                    )
            if self.chiller_connected:
                chiller_watchdog = self.chiller_model.get_watchdog()
                if chiller_watchdog.alarmsPresent:
                    raise RuntimeError(
                        "Can't go to standby: chiller is reporting one or more alarms"
                    )
        if self.lamp_connected:
            remaining_cooldown = self.lamp_model.get_remaining_cooldown()
            if remaining_cooldown > 0:
                raise salobj.ExpectedError(
                    "The lamp is cooling. You can't go to standby "
                    "until the chiller has run for another "
                    f"{remaining_cooldown:0.2f} seconds."
                )

    async def start(self):
        await super().start()
        await self.evt_lampConnected.set_write(connected=False)
        await self.evt_chillerConnected.set_write(connected=False)
        await self.evt_lampState.set_write(
            basicState=LampBasicState.UNKNOWN,
            controllerState=LampControllerState.UNKNOWN,
            controllerError=LampControllerError.UNKNOWN,
        )
        await self.evt_shutterState.set_write(
            commandedState=ShutterState.UNKNOWN,
            actualState=ShutterState.UNKNOWN,
            enabled=False,
        )

    async def close_tasks(self):
        await self.disconnect_chiller()
        await self.disconnect_lamp()
        await super().close_tasks()

    async def do_closeShutter(self, data):
        """Close the shutter.

        Parameters
        ----------
        data : salobj.BaseMsgType
            Command data; ignored.
        """
        self.assert_enabled()
        if not self.lamp_connected:
            raise salobj.ExpectedError("Lamp not connected")
        await self.cmd_openShutter.ack_in_progress(
            data=data, timeout=self.config.lamp.shutter_timeout
        )
        await self.lamp_model.move_shutter(do_open=False)

    async def do_openShutter(self, data):
        """Open the shutter.

        Parameters
        ----------
        data : salobj.BaseMsgType
            Command data; ignored.
        """
        self.assert_enabled()
        if not self.lamp_connected:
            raise salobj.ExpectedError("Lamp not connected")
        await self.cmd_openShutter.ack_in_progress(
            data=data, timeout=self.config.lamp.shutter_timeout
        )
        await self.lamp_model.move_shutter(do_open=True)

    async def do_turnLampOn(self, data):
        """Turn on the lamp.

        Rejected if the lamp is cooling down.

        Parameters
        ----------
        data : salobj.BaseMsgType
            Command data; ignored.
        """
        self.assert_enabled()
        # make sure the chiller is running, and not reporting any alarms
        if not self.lamp_connected:
            raise salobj.ExpectedError("Lamp not connected")
        if not self.chiller_connected:
            raise salobj.ExpectedError("Chiller not connected")
        chiller_watchdog = self.chiller_model.get_watchdog()
        if chiller_watchdog.alarmsPresent:
            raise salobj.ExpectedError("Chiller is reporting an alarm.")
        if chiller_watchdog.controllerState != ChillerControllerState.RUN:
            raise salobj.ExpectedError("Chiller not running.")
        if not chiller_watchdog.pumpRunning:
            raise salobj.ExpectedError("Chiller pump not running.")
        if data.power == 0:
            power = self.config.lamp.default_power
        else:
            power = data.power
        await self.cmd_turnLampOn.ack_in_progress(
            data=data,
            timeout=self.config.lamp.max_lamp_on_delay + ONOFF_COMMAND_TIMEOUT_MARGIN,
        )
        self.log.info(f"Turn lamp on with {power=}.")
        await self.lamp_model.turn_lamp_on(power=power)
        self.log.info("Lamp should be on.")

    async def do_turnLampOff(self, data):
        """Turn off the lamp.

        Rejected if the lamp is warming up, unless you specify
        force=True

        Parameters
        ----------
        data : salobj.BaseMsgType
            Command data.
        """
        self.assert_enabled()
        if not self.lamp_connected:
            raise salobj.ExpectedError("Lamp not connected")
        await self.cmd_turnLampOff.ack_in_progress(
            data=data,
            timeout=self.config.lamp.max_lamp_off_delay + ONOFF_COMMAND_TIMEOUT_MARGIN,
        )
        # Note: ``reason`` is used if an existing turnLampOn command
        # has to be aborted; hence the use of "Superseded".
        await self.lamp_model.turn_lamp_off(
            force=data.force, wait=True, reason="Superseded by a turnLampOff command"
        )

    async def do_setChillerTemperature(self, data):
        """Sets the target temperature for the chiller

        Parameters
        ----------
        data : salobj.BaseMsgType
            Command data.
        """
        self.assert_enabled()
        if data.temperature > self.config.chiller.high_supply_temperature_warning:
            raise salobj.ExpectedError(
                f"temperature={data.temperature} > "
                f"high_supply_temperature_warning={self.config.chiller.high_supply_temperature_warning}"
            )
        elif data.temperature < self.config.chiller.low_supply_temperature_warning:
            raise salobj.ExpectedError(
                f"temperature={data.temperature} < "
                f"low_supply_temperature_warning={self.config.chiller.low_supply_temperature_warning}"
            )
        if not self.chiller_connected:
            raise salobj.ExpectedError("Chiller not connected")
        await self.chiller_model.do_set_control_temperature(data.temperature)

    async def do_startChiller(self, data):
        """Command the chiller to start cooling.

        Parameters
        ----------
        data : salobj.BaseMsgType
            Command data; ignored.
        """
        self.assert_enabled()
        if not self.chiller_connected:
            raise salobj.ExpectedError("Chiller not connected")
        await self.chiller_model.start_cooling()

    async def do_stopChiller(self, data):
        """Command the chiller to stop cooling.

        Rejected if the lamp is on or was turned off within
        configuration parameter ``cooldown_period`` seconds.

        Parameters
        ----------
        data : salobj.BaseMsgType
            Command data; ignored.
        """
        self.assert_enabled()
        if not self.chiller_connected:
            raise salobj.ExpectedError("Chiller not connected")
        if self.lamp_connected:
            if self.lamp_model.lamp_was_on:
                raise salobj.ExpectedError("Can't stop cooling while the lamp is on")
            remaining = self.lamp_model.get_remaining_cooldown()
            if remaining > 0:
                raise salobj.ExpectedError(
                    "Lamp is cooling down; "
                    f"you can't stop the chiller for {remaining:0.2f} seconds"
                )
        await self.chiller_model.stop_cooling()

    async def status_callback(self, _):
        """Callback function for state changes in lamp and chiller.

        Go to fault state if the system has problems.

        The argument is the model reporting the state change.
        It is ignored.
        """
        if self.summary_state == salobj.State.FAULT:
            return

        if not self.should_be_connected:
            return

        # Handle reasons to go to fault state
        if not self.lamp_connected:
            return await self.fault(
                code=ErrorCode.LAMP_DISCONNECTED,
                report="Lamp controller disconnected",
            )

        if not self.chiller_connected:
            return await self.fault(
                code=ErrorCode.CHILLER_DISCONNECTED,
                report="Chiller controller disconnected",
            )

        lamp_state = self.lamp_model.get_state()
        if lamp_state.controllerError != LampControllerError.NONE:
            # Don't report the lamp error code in ``reason``
            # because it will almost always be UNKNOWN
            # (the blinking error signal won't have been decoded yet)
            # and that is not useful information.
            return await self.fault(
                code=ErrorCode.LAMP_ERROR,
                report="Lamp controller is reporting an error",
            )

        # Fault if the lamp is unexpectedly on or off
        if lamp_state.basicState == LampBasicState.UNEXPECTEDLY_ON:
            return await self.fault(
                code=ErrorCode.LAMP_UNEXPECTEDLY_ON,
                report="Lamp is on when it should be off. The lamp controller may be stuck on.",
            )
        elif lamp_state.basicState == LampBasicState.UNEXPECTEDLY_OFF:
            return await self.fault(
                code=ErrorCode.LAMP_UNEXPECTEDLY_OFF,
                report="Lamp is off when it should be on. Check the lamp and lamp controller.",
            )

        chiller_watchdog = self.chiller_model.get_watchdog()
        if chiller_watchdog.alarmsPresent:
            return await self.fault(
                code=ErrorCode.CHILLER_ERROR, report="Chiller reporting alarms"
            )

        # Fault if the lamp is on and the chiller is not chilling
        if self.lamp_model.lamp_was_on:
            if chiller_watchdog.controllerState != ChillerControllerState.RUN:
                return await self.fault(
                    code=ErrorCode.NOT_CHILLING_WITH_LAMP_ON,
                    report="Chiller is not running; "
                    f"controller state={chiller_watchdog.controllerState!r}",
                )
            if not chiller_watchdog.pumpRunning:
                return await self.fault(
                    code=ErrorCode.NOT_CHILLING_WITH_LAMP_ON,
                    report="Chiller pump is off",
                )


def run_atwhitelight() -> None:
    """Run the ATWhiteLight CSC."""
    asyncio.run(ATWhiteLightCsc.amain(index=None))
