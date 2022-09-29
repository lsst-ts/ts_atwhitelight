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

__all__ = ["LampModel"]

import asyncio
import inspect

from .labjack_interface import LabJackInterface

from lsst.ts import salobj
from lsst.ts import utils
from lsst.ts.idl.enums.ATWhiteLight import (
    LampBasicState,
    LampControllerState,
    LampControllerError,
    ShutterState,
)
from .lamp_base import (
    ERROR_BLINKING_DURATION,
    STATUS_INTERVAL,
    SHUTTER_ENABLE,
    SHUTTER_DISABLE,
    SHUTTER_OPEN,
    SHUTTER_CLOSE,
    MIN_POWER,
    MAX_POWER,
    voltage_from_power,
)


def offset_timestamp(timestamp, offset):
    """Return timestamp if 0, else timestamp + offset.

    The purpose of this function is to report 0 as 0,
    instead of some unrealistic tiny value.
    """
    if timestamp == 0:
        return 0
    return timestamp + offset


class LampModel:
    """Interface to a Horiba KiloArc white light controller.

    Keep track of the state and enforce warmup and cooldown periods
    described in the User's Guide

    Parameters
    ----------
    config : `types.SimpleNamespace`
        Lamp-specific configuration.
    topics : `lsst.ts.salobj.BaseCsc` or `types.SimpleNamespace`
        The CSC or a struct with lamp-specific write topics.
    log : `logging.Logger`
        Logger
    status_callback : `awaitable` or `None`, optional
        Coroutine to call when evt_lampState or evt_lampConnected changes.
        It receives one argument: this model.
    simulate : `bool`, optional
        Run in simulation mode?

    Raises
    ------
    TypeError
        If ``status_callback`` is not None and not a coroutine.
    ValueError
        If ``config.default_power`` not in range [800, 1200], inclusive.

    Attributes
    ----------
    default_power : float 800-1200
        Default power after the lamp is started (Watts)
    off_time : float
        Time at which the lamp was last turned off (TAI unix seconds)
    on_time : float
        Time at which the lamp was last turned on (TAI unix seconds)
    """

    def __init__(self, config, topics, log, status_callback=None, simulate=False):
        if status_callback is not None and not inspect.iscoroutinefunction(
            status_callback
        ):
            raise TypeError(
                f"status_callback={status_callback} must be None or a coroutine"
            )
        if config.default_power < 800 or config.default_power > 1200:
            raise ValueError(
                f"config.lamp.default_power={config.default_power} must be "
                "in range [800, 1200], inclusive."
            )

        self.config = config
        self.topics = topics
        self.log = log.getChild("LampModel")
        self.simulate = simulate
        self.status_callback = status_callback

        # Set True if you call evt_lampState.set and it changes something
        self.force_next_state_output = False

        # Set if connected to the labjack and state data seen,
        # cleared otherwise.
        self.status_event = asyncio.Event()

        self.labjack = LabJackInterface(
            identifier=self.config.identifier,
            log=self.log,
            device_type=self.config.device_type,
            connection_type=self.config.connection_type,
            simulate=simulate,
        )
        self.simulate = False
        self.status_task = utils.make_done_future()
        self.lamp_on = False
        self.lamp_off_time = 0
        self.lamp_on_time = 0
        # Set this true any time the blinking error signal is off
        # for at least ERROR_BLINKING_DURATION seconds.
        # This helps decode error signals.
        # Initialize to False in case the lamp controller is reporting
        # an error when we first connect.
        self.blinking_error_gap_seen = False
        # Interval between querying the LabJack (seconds).
        # This must be less than 0.25 in order to reliably
        # read the controller's blinking error signal.
        self.status_interval = STATUS_INTERVAL

        # Was the blinking error signal on last time status was read?
        self.blinking_error_was_on = False
        # Time at which the blinking error signal
        # most recently switched from off to on
        self.blinking_error_on_time = 0
        # Time at which the blinking error signal
        # most recently switched from on to off
        self.blinking_error_off_time = 0
        # Time at which the blinking error signal started blinking;
        # reset after the blinking stops and the error code has been read.
        self.error_code_start_time = 0

        # Events for the switches that detect that the shutter
        # is fully open and fully closed.
        # Set by status_loop and cleared by move_shutter.
        self.shutter_open_event = asyncio.Event()
        self.shutter_closed_event = asyncio.Event()

    @property
    def connected(self):
        """Return True if connected to the LabJack."""
        return self.labjack.connected

    @property
    def status_seen(self):
        """Return True if connected and status has been seen."""
        return self.connected and self.status_event.is_set()

    def get_state(self):
        """Get the current evt_lampState data.

        Raise RuntimeError if not connected or if state data
        has not been seen since the connection was made
        (which would be a bug, since the model should not report
        being connected until state data is seen).
        """
        if not self.connected:
            raise RuntimeError("Not connected")
        if not self.status_event.is_set() or not self.topics.evt_lampState.has_data:
            raise RuntimeError("Status not yet seen")
        return self.topics.evt_lampState.data

    async def connect(self):
        await asyncio.wait_for(
            self.basic_connect(), timeout=self.config.connect_timeout
        )

    async def basic_connect(self):
        self.status_event.clear()
        await self.labjack.connect()
        self.status_task = asyncio.create_task(self.status_loop())
        await self.status_event.wait()

    async def disconnect(self):
        self.force_next_state_output = False
        await asyncio.wait_for(
            self.basic_disconnect(), timeout=self.config.connect_timeout
        )

    async def basic_disconnect(self):
        await self.turn_lamp_off(force=True)
        self.status_task.cancel()
        self.status_event.clear()
        await self.labjack.disconnect()
        await self.set_status(
            controller_state=LampControllerState.UNKNOWN,
            controller_error=LampControllerError.UNKNOWN,
        )

    async def status_loop(self):
        """Monitor the status.

        Also set the power to default_power if warmup is done.
        Doing it here makes sure that when basicState goes from warmup to on,
        that other values match.
        """
        try:
            while True:
                data = await self.labjack.read()
                current_tai = utils.current_tai()

                if data.error_exists:
                    # Try to decode the blinking error
                    if self.topics.evt_lampState.has_data:
                        controller_error = (
                            self.topics.evt_lampState.data.controllerError
                        )
                    else:
                        controller_error = LampControllerError.NONE
                    if data.blinking_error:
                        if not self.blinking_error_was_on:
                            self.blinking_error_on_time = current_tai
                            if (
                                self.blinking_error_gap_seen
                                and current_tai - self.blinking_error_off_time
                                > ERROR_BLINKING_DURATION
                            ):
                                self.log.debug("Blinking error signal has started")
                                # Blinking error is starting to report a code
                                self.error_code_start_time = current_tai

                        if (
                            self.status_event.is_set()
                            and controller_error == LampControllerError.NONE
                        ):
                            # This is a new error (otherwise we assume that the
                            # existing error code is still correct, until
                            # we finish counting blinks and know for sure).
                            controller_error = LampControllerError.UNKNOWN
                    else:
                        if self.blinking_error_was_on:
                            self.blinking_error_off_time = current_tai
                        else:
                            off_duration = current_tai - self.blinking_error_off_time
                            if off_duration < ERROR_BLINKING_DURATION:
                                # Blinking error may still be reporting a code
                                pass
                            else:
                                if self.error_code_start_time > 0:
                                    # We are trying decode an error code
                                    # and the error signal has been off
                                    # long enough to do it.
                                    # The controller reports an error
                                    # by blinking the error signal N times,
                                    # 0.5 seconds on, 0.5 seconds off,
                                    # then waiting 1.5 seconds and repeating.
                                    # Since each blink cycle is 1 second long,
                                    # the number of blinks equals the number
                                    # of seconds since the blinking began
                                    # plus 0.5 for the final blink's off time.
                                    float_code_duration = (
                                        0.5
                                        + self.blinking_error_off_time
                                        - self.error_code_start_time
                                    )
                                    int_code_duration = int(
                                        round(float_code_duration, 0)
                                    )
                                    try:
                                        controller_error = LampControllerError(
                                            int_code_duration
                                        )
                                    except ValueError:
                                        self.log.warning(
                                            f"Unrecognized error code duration: {int_code_duration}; "
                                            "leaving error as UNKNOWN"
                                        )
                                        controller_error = LampControllerError.UNKNOWN
                                    self.error_code_start_time = 0
                    self.blinking_error_was_on = data.blinking_error
                else:
                    # Ignore the blinking error, which should be off
                    controller_error = LampControllerError.NONE
                    self.error_code_start_time = 0
                    self.blinking_error_on_time = 0
                    self.blinking_error_off_time = 0
                    self.blinking_error_was_on = False
                    self.blinking_error_gap_seen = True

                if data.error_exists:
                    controller_state = LampControllerState.ERROR
                elif data.standby_or_on:
                    controller_state = LampControllerState.STANDBY_OR_ON
                elif data.cooldown:
                    controller_state = LampControllerState.COOLDOWN
                else:
                    controller_state = LampControllerState.OFF

                shutter_state = {
                    (False, False): ShutterState.UNKNOWN,
                    (True, False): ShutterState.CLOSED,
                    (False, True): ShutterState.OPEN,
                    (True, True): ShutterState.INVALID,
                }[(bool(data.shutter_closed), bool(data.shutter_open))]
                await self.set_status(
                    controller_state=controller_state,
                    controller_error=controller_error,
                )
                await self.topics.evt_shutterState.set_write(actualState=shutter_state)
                if bool(data.shutter_closed):
                    self.shutter_closed_event.set()
                if bool(data.shutter_open):
                    self.shutter_open_event.set()
                self.status_event.set()
                await asyncio.sleep(self.status_interval)
        except asyncio.CancelledError:
            self.log.debug("Status loop ends")
        except Exception:
            self.log.exception("Status loop failed")
            await self.disconnect()
            raise

    async def set_status(self, controller_state, controller_error):
        """Set status and, if changed, call the status callback.

        Parameters
        ----------
        controller_error : `LampControllerError`
            Error reported by the lamp controller.
        controller_state : `LampControllerState`
            Lamp controller state.
        """
        current_tai = utils.current_tai()
        controller_cooling = controller_state == LampControllerState.COOLDOWN

        on_seconds = 0
        if self.topics.evt_lampState.has_data:
            power = self.topics.evt_lampState.data.setPower
            if power > 0:
                if not self.lamp_on:
                    self.lamp_on = True
                    self.lamp_on_time = current_tai
            else:
                if self.lamp_on:
                    self.lamp_on = False
                    self.lamp_off_time = current_tai
                    on_seconds = self.lamp_off_time - self.lamp_on_time

        if self.lamp_on:
            if self.get_remaining_warmup() > 0:
                basic_state = LampBasicState.WARMUP
            else:
                basic_state = LampBasicState.ON
        else:
            if self.get_remaining_cooldown() > 0:
                basic_state = LampBasicState.COOLDOWN
            elif controller_cooling:
                self.log.info(
                    "Setting lampState.basicState=COOLDOWN because "
                    "lamp controller is in cooldown"
                )
                basic_state = LampBasicState.COOLDOWN
            else:
                basic_state = LampBasicState.OFF

        result1 = await self.topics.evt_lampState.set_write(
            basicState=basic_state,
            controllerError=controller_error,
            controllerState=controller_state,
            cooldownEndTime=offset_timestamp(
                self.lamp_off_time, self.config.cooldown_period
            ),
            warmupEndTime=offset_timestamp(
                self.lamp_on_time, self.config.warmup_period
            ),
            force_output=self.force_next_state_output,
        )
        self.force_next_state_output = False

        result2 = await self.topics.evt_lampConnected.set_write(
            connected=self.labjack.connected
        )

        if on_seconds > 0:
            await self.topics.evt_lampOnHours.set_write(hours=on_seconds / 3600)

        if result1.did_change or result2.did_change:
            await self.call_status_callback()

    def get_remaining_cooldown(self, tai=None):
        """Return the remaining cooldown duration (seconds), or 0 if none.

        Parameters
        ----------
        tai : `float` or `None`, optional
            TAI time (unix seconds).
        """
        if tai is None:
            tai = utils.current_tai()
        off_duration = tai - self.lamp_off_time
        return max(0, self.config.cooldown_period - off_duration)

    def get_remaining_warmup(self, tai=None):
        """Return the remaining warmup duration (seconds), or 0 if none.

        Parameters
        ----------
        tai : `float` or `None`, optional
            TAI time (unix seconds).
        """
        if tai is None:
            tai = utils.current_tai()
        on_duration = tai - self.lamp_on_time
        return max(0, self.config.warmup_period - on_duration)

    async def move_shutter(self, do_open):
        """Open or close the shutter.

        Parameters
        ----------
        do_open : `bool`
            Specify True to open the shutter, False to close it.

        Raises
        ------
        asyncio.TimeoutError
            If the shutter does not fully open or close in time
            specified by config.shutter_timeout.
            If this happens the motor is disabled.
        lsst.ts.salobj.ExpectedError
            If both shutter sensing switches are active.
        """
        desired_state = ShutterState.OPEN if do_open else ShutterState.CLOSED
        if self.topics.evt_shutterState.has_data:
            if (
                self.topics.evt_shutterState.data.commandedState == desired_state
                and self.topics.evt_shutterState.data.actualState == desired_state
            ):
                # Already done
                return
            if self.topics.evt_shutterState.data.actualState == ShutterState.INVALID:
                raise salobj.ExpectedError(
                    "One or both shutters sensing switches is broken; "
                    "cannot move the shutter"
                )
        shutter_event = (
            self.shutter_open_event if do_open else self.shutter_closed_event
        )
        await self.labjack.write(
            shutter_direction=SHUTTER_OPEN if do_open else SHUTTER_CLOSE
        )
        await self.labjack.write(shutter_enable=SHUTTER_ENABLE)
        await self.topics.evt_shutterState.set_write(
            commandedState=desired_state, enabled=True, force_output=True
        )
        shutter_event.clear()
        try:
            await asyncio.wait_for(
                shutter_event.wait(), timeout=self.config.shutter_timeout
            )
        except asyncio.TimeoutError:
            movestr = "open" if do_open else "close"
            self.log.error(
                f"Shutter failed to {movestr} "
                f"in config.shutter_timeout={self.config.shutter_timeout:0.2f} seconds"
            )
            raise
        finally:
            await self.labjack.write(shutter_enable=SHUTTER_DISABLE)
            await self.topics.evt_shutterState.set_write(enabled=False)

        if self.topics.evt_shutterState.data.actualState == ShutterState.INVALID:
            raise salobj.ExpectedError(
                "One or both shutters sensing switches is broken; move failed"
            )

    async def turn_lamp_on(self, power):
        """Turn the lamp on or change the power.

        Note that the lamp will be ignited at 1200W,
        then fall back to the specified power 2-20 seconds later.

        Parameters
        ----------
        power : `float`
            Lamp power. Must be in the range [800, 1200] W, inclusive.

        Raises
        ------
        salobj.ExpectedError
            If the lamp is already on, or is off but still cooling down.
        """
        if power < MIN_POWER or power > MAX_POWER:
            raise salobj.ExpectedError(
                f"{power} must be in range [{MIN_POWER}, {MAX_POWER}], inclusive"
            )
        remaining_cooldown = self.get_remaining_cooldown()
        if remaining_cooldown > 0:
            raise salobj.ExpectedError(
                f"Cooling; wait {remaining_cooldown:0.1f} seconds."
            )

        await self._basic_set_power(power)

    async def turn_lamp_off(self, force=False):
        """Turn the lamp off (if on). Fail if warming up, unless force=True.

        Parameters
        ----------
        force : `bool`
            Force the lamp off, even if warming up.
            This can significantly reduce bulb life.

        Raises
        ------
        salobj.ExpectedError
            If warming up and force=False.
        """
        if not self.lamp_on:
            return

        on_duration = utils.current_tai() - self.lamp_on_time
        remaining_warmup_duration = self.config.warmup_period - on_duration
        if remaining_warmup_duration > 0:
            if force:
                self.log.warning(
                    "Turning off lamp while warming up because force=True; "
                    f"remaining warmup duration={remaining_warmup_duration:0.1f} seconds"
                )
            else:
                raise salobj.ExpectedError(
                    f"Can't power off lamp while warming up; "
                    f"wait {remaining_warmup_duration:0.1f} seconds or use force=True."
                )

        await self._basic_set_power(0)

    async def _basic_set_power(self, power):
        """Set the desired lamp power.

        This routine does not check that the specified power is in range.
        That is done in set_power.

        Parameters
        ----------
        power : `float`
            Desired power (W). Specify 0 to turn the lamp off.
            Otherwise specify a value between 800 and 1200W (inclusive).

        Raises
        ------
        lsst.ts.salobj.ExpectedError
            If power is not 0 and is not between 800 and 1200W (inclusive).
        """
        voltage = voltage_from_power(power)
        await self.labjack.write(set_power=voltage)

        # Rather than calling set_status wait for the next polling
        # so the data is self-consistent. But do force output
        # if setPower changed, in case this is the only change.
        did_change = self.topics.evt_lampState.set(setPower=power)
        self.force_next_state_output = self.force_next_state_output or did_change

    async def call_status_callback(self):
        """Call the status callback, if there is one."""
        if self.status_callback is None:
            return
        try:
            await self.status_callback(self)
        except Exception:
            self.log.exception("status callback failed")
