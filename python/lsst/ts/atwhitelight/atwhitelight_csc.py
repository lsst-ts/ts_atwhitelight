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

__all__ = ["ATWhiteLightCsc", "run_atwhitelight"]

import asyncio
import copy
import types

from lsst.ts import salobj
from lsst.ts.idl.enums.ATWhiteLight import (
    ChillerControllerState,
    ErrorCode,
    LampControllerError,
    ShutterState,
)
from .lamp_model import LampModel
from .chiller_model import ChillerModel
from .config_schema import CONFIG_SCHEMA
from . import __version__


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

        # Set True just after the lamp and chiller are both connected,
        # and false just before disconnecting them.
        self.should_be_connected = False

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
                await self.connect_chiller()
            if self.summary_state == salobj.State.ENABLED:
                chiller_watchdog = self.chiller_model.get_watchdog()
                if chiller_watchdog.alarmsPresent:
                    return await self.fault(
                        code=ErrorCode.CHILLER_ERROR,
                        report="Chiller is reporting alarms",
                    )
            if not self.lamp_connected:
                await self.connect_lamp()
            self.should_be_connected = True
        elif self.summary_state == salobj.State.FAULT:
            # Turn off the lamp, if connected
            if self.lamp_connected and self.lamp_model.lamp_on:
                self.log.warning(
                    "Going to fault while connected to the lamp controller; "
                    "forcing the lamp off"
                )
                await self.lamp_model.turn_lamp_off(force=True)
            else:
                self.log.warning(
                    "Going to fault and not connect to the lamp controller; "
                    "please turn the lamp off manually."
                )
        else:
            self.should_be_connected = False
            if self.lamp_connected and self.lamp_model.lamp_on:
                await self.lamp_model.turn_lamp_off(force=True)
            await self.disconnect_lamp()
            await self.disconnect_chiller()

    async def connect_chiller(self):
        await self.disconnect_chiller()
        if self.chiller_model is None:
            self.chiller_model = ChillerModel(
                config=self.config.chiller,
                topics=self,
                log=self.log,
                status_callback=self.status_callback,
                simulate=self.simulation_mode != 0,
            )
        await self.chiller_model.connect()

    async def connect_lamp(self):
        await self.disconnect_lamp()
        if self.lamp_model is None:
            labjack_config = self.config.lamp
            self.lamp_model = LampModel(
                config=labjack_config,
                topics=self,
                log=self.log,
                status_callback=self.status_callback,
                simulate=self.simulation_mode != 0,
            )
        await self.lamp_model.connect()

    async def disconnect_chiller(self):
        # Don't use chiller_connected because that can be false
        # even if a basic connection exists (before status seen)
        if self.chiller_model is None:
            return
        await self.chiller_model.disconnect()

    async def disconnect_lamp(self):
        # Don't use lamp_connected because that can be false
        # even if a basic connection exists (before status seen)
        if self.lamp_model is None:
            return
        await self.lamp_model.disconnect()

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
        await self.lamp_model.turn_lamp_on(power=power)

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
        await self.lamp_model.turn_lamp_off(force=data.force)

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
            if self.lamp_model.lamp_on:
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

        chiller_watchdog = self.chiller_model.get_watchdog()
        if chiller_watchdog.alarmsPresent:
            return await self.fault(
                code=ErrorCode.CHILLER_ERROR, report="Chiller reporting alarms"
            )

        # Fault if the lamp is on and the chiller is not chilling
        if self.lamp_model.lamp_on:
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
