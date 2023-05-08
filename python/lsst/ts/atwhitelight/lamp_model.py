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

from lsst.ts import salobj, utils
from lsst.ts.idl.enums.ATWhiteLight import (
    LampBasicState,
    LampControllerError,
    LampControllerState,
    ShutterState,
)

from .labjack_interface import LabJackInterface
from .lamp_base import (
    ERROR_BLINKING_DURATION,
    MAX_POWER,
    MIN_POWER,
    SHUTTER_CLOSE,
    SHUTTER_DISABLE,
    SHUTTER_ENABLE,
    SHUTTER_OPEN,
    STATUS_INTERVAL,
    VOLTS_AT_MIN_POWER,
    power_from_voltage,
    voltage_from_power,
)
from .mock_labjack_interface import MockLabJackInterface

# How long (sec) after writing new power to the LabJack before reading it.
READ_POWER_DELAY = 0.1

# How much longer (sec) than the max timeout to wait for a lamp on or off
# command to time out. The margin is intended to avoid a race condition,
# while also protecting against bugs that could cause an indefinite hang.
ONOFF_COMMAND_TIMEOUT_MARGIN = 2

# What set lamp voltage indicates that the lamp is commanded to be on?
# This should be a bit less than the actual min voltage, to allow for
# quantization error and electrical noise (if reading a sense line instead
# of the output DAC register). Note that the set voltage should
# either be 0 or >= VOLTS_AT_MIN_POWER, so there should never be any doubt
# as to whether the lamp has been commanded on.
LAMP_SET_VOLTAGE_ON_THRESHOLD = VOLTS_AT_MIN_POWER - 0.1


def offset_timestamp(timestamp, offset):
    """Return timestamp if 0, else timestamp + offset.

    The purpose of this function is to report timestamp=0 as 0,
    instead of some unrealistic tiny value (offset).
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
    csc : `lsst.ts.salobj.BaseCsc`
        The CSC. This class writes to lamp-specific event topics
        and reads and writes two additional float attributes:
        ``lamp_on_time`` and ``lamp_off_time``.
    log : `logging.Logger`
        Logger.
    status_callback : `awaitable` or `None`, optional
        Coroutine to call when evt_lampState or evt_lampConnected changes.
        It receives one argument: this model.
    simulate : `bool`, optional
        Run in simulation mode?
    make_connect_time_out : `bool`, optional
        Make the connect method timeout?
        Only useful for unit tests.
        Ignored if simulate false.

    Raises
    ------
    TypeError
        If ``status_callback`` is not None and not a coroutine.
    ValueError
        If ``config.default_power`` not in range [800, 1200], inclusive.

    Attributes
    ----------
    default_power : `float`
        Default power after the lamp is started (Watts) in range 800-1200.
    lamp_was_on : `bool`
        Was the lamp commanded on, as of the most recently read LabJack data?
    """

    def __init__(
        self,
        config,
        csc,
        log,
        status_callback=None,
        simulate=False,
        make_connect_time_out=False,
    ):
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
        self.csc = csc
        self.log = log.getChild("LampModel")
        self.make_connect_time_out = make_connect_time_out
        self.status_callback = status_callback

        # Set if connected to the labjack and state data seen,
        # cleared otherwise.
        self.status_event = asyncio.Event()

        if simulate:
            interface_class = MockLabJackInterface
        else:
            interface_class = LabJackInterface
        self.labjack = interface_class(
            identifier=self.config.identifier,
            log=self.log,
            device_type=self.config.device_type,
            connection_type=self.config.connection_type,
            simulate=simulate,
        )
        self.status_task = utils.make_done_future()
        self.lamp_was_on = None
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

        # Lock for READ_POWER_DELAY when writing new power to the LabJack
        # and lock before reading power, so the read power will match.
        self.change_power_lock = asyncio.Lock()

        self.lamp_unexpectedly_off = False
        self.lamp_unexpectedly_on = False

        # Futures to keep track of when the lamp actually goes on or off.
        # Used by the CSC to delay the final ack for turnLampOn and turnLampOff
        # commands. To terminate these, call abort_lamp_on/off_future
        # (instead of cancelling) in order to provide good feedback
        # for the turnLampOn or turnLampOff commands.
        self.lamp_on_future = utils.make_done_future()
        self.lamp_off_future = utils.make_done_future()

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
    def simulate(self):
        """Return the simulate constructor argument."""
        return self.labjack.simulate

    @property
    def status_seen(self):
        """Return True if connected and status has been seen."""
        return self.connected and self.status_event.is_set()

    @property
    def lamp_off_time(self):
        """Get the lamp off time, or 0 if unknown."""
        return self.csc.lamp_off_time

    @property
    def lamp_on_time(self):
        """Get the lamp on time, or 0 if unknown."""
        return self.csc.lamp_on_time

    @lamp_off_time.setter
    def lamp_off_time(self, lamp_off_time):
        self.csc.lamp_off_time = lamp_off_time

    @lamp_on_time.setter
    def lamp_on_time(self, lamp_on_time):
        self.csc.lamp_on_time = lamp_on_time

    def abort_lamp_on_future(self, reason):
        """Abort self.lamp_on_future (if not done) with a salobj.ExpectedError
        exception.

        Parameters
        ----------
        reason : `str`
            The text for the exception.
        """
        if not self.lamp_on_future.done():
            self.lamp_on_future.set_exception(salobj.ExpectedError(reason))

    def abort_lamp_off_future(self, reason):
        """Abort self.lamp_off_future (if not done) with a salobj.ExpectedError
        exception.

        Parameters
        ----------
        reason : `str`
            The text for the exception.
        """
        if not self.lamp_off_future.done():
            self.lamp_off_future.set_exception(salobj.ExpectedError(reason))

    def get_state(self):
        """Get the current evt_lampState data.

        Raise RuntimeError if not connected or if state data
        has not been seen since the connection was made
        (which would be a bug, since the model should not report
        being connected until state data is seen).
        """
        if not self.connected:
            raise RuntimeError("Not connected")
        if not self.status_event.is_set() or not self.csc.evt_lampState.has_data:
            raise RuntimeError("Status not yet seen")
        return self.csc.evt_lampState.data

    async def connect(self):
        self.abort_lamp_on_future("Connecting to the lamp controller")
        self.abort_lamp_off_future("Connecting to the lamp controller")
        try:
            await self.basic_disconnect(cancel_status_loop=False)
            self.lamp_unexpectedly_off = False
            self.lamp_unexpectedly_on = False
            if self.simulate and self.make_connect_time_out:
                raise asyncio.TimeoutError(
                    "LampModel.connect timing out because make_connect_time_out is true"
                )
            await asyncio.wait_for(
                self.basic_connect(), timeout=self.config.connect_timeout
            )
        except Exception as e:
            self.log.exception(f"LampModel.connect failed: {e!r}")
            await self.call_status_callback()
            raise

    async def basic_connect(self):
        self.status_event.clear()
        await self.labjack.connect()
        self.status_task = asyncio.create_task(self.status_loop())
        await self.status_event.wait()

    async def disconnect(self, cancel_status_loop=True):
        try:
            was_connected = self.connected
            await asyncio.wait_for(
                self.basic_disconnect(cancel_status_loop=cancel_status_loop),
                timeout=self.config.connect_timeout,
            )
            if was_connected:
                await self.call_status_callback()
        except Exception as e:
            self.log.exception(f"LampModel.disconnect failed: {e!r}")
            await self.call_status_callback()
            raise

    async def basic_disconnect(self, cancel_status_loop):
        if self.connected:
            await self.turn_lamp_off(
                force=True, wait=False, reason="Disconnecting from the lamp controller"
            )
        # Paranoia; these futures should both be done.
        self.abort_lamp_on_future("Disconnecting from the lamp controller")
        self.abort_lamp_off_future("Disconnecting from the lamp controller")
        if cancel_status_loop:
            self.status_task.cancel()
            self.status_event.clear()
        await self.labjack.disconnect()
        await self.set_status(
            controller_state=LampControllerState.UNKNOWN,
            controller_error=LampControllerError.UNKNOWN,
            light_detected=False,  # Ignored
            read_lamp_set_voltage=0,  # Ignored
        )

    async def status_loop(self):
        """Monitor the status.

        Also set the power to default_power if warmup is done.
        Doing it here makes sure that when basicState goes from warmup to on,
        that other values match.
        """
        try:
            while True:
                async with self.change_power_lock:
                    data = await self.labjack.read()
                current_tai = utils.current_tai()
                if data.error_exists:
                    # Try to decode the blinking error
                    if self.csc.evt_lampState.has_data:
                        controller_error = self.csc.evt_lampState.data.controllerError
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
                    # Apparently none of the status LEDs is on.
                    # Likely the lamp controller is powered off,
                    # or a connection between the lamp controller
                    # and the LabJack is broken.
                    controller_state = LampControllerState.UNKNOWN

                shutter_state = {
                    (False, False): ShutterState.UNKNOWN,
                    (True, False): ShutterState.CLOSED,
                    (False, True): ShutterState.OPEN,
                    (True, True): ShutterState.INVALID,
                }[(bool(data.shutter_closed), bool(data.shutter_open))]
                light_detected = data.photosensor > self.config.photo_sensor_on_voltage
                await self.set_status(
                    controller_state=controller_state,
                    controller_error=controller_error,
                    light_detected=light_detected,
                    read_lamp_set_voltage=data.read_lamp_set_voltage,
                )
                await self.csc.evt_shutterState.set_write(actualState=shutter_state)
                if bool(data.shutter_closed):
                    self.shutter_closed_event.set()
                if bool(data.shutter_open):
                    self.shutter_open_event.set()
                self.status_event.set()
                await asyncio.sleep(self.status_interval)
        except asyncio.CancelledError:
            self.log.debug("Status loop ends")
        except Exception as e:
            error_message = f"Status loop failed; disconnecting: {e!r}"
            self.log.exception(error_message)
            self.abort_lamp_on_future(error_message)
            self.abort_lamp_off_future(error_message)
            await self.disconnect(cancel_status_loop=False)
            raise
        self.abort_lamp_on_future("Data client shutting down: status loop ends")
        self.abort_lamp_off_future("Data client shutting down: status loop ends")

    async def set_status(
        self,
        controller_state,
        controller_error,
        light_detected,
        read_lamp_set_voltage,
    ):
        """Set status and, if changed, call the status callback.

        Parameters
        ----------
        controller_error : `LampControllerError`
            Error reported by the lamp controller.
            Ignored if not connected.
        controller_state : `LampControllerState`
            Lamp controller state.
            Ignored if not connected.
        light_detected : `bool`
            Did the photo sensor detect light?
            Ignored if not connected.
        lamp_commanded_on : `bool`
            Is the lamp commanded to be on? This should be based on
            ``read_lamp_set_voltage`` from the LabJack.
             Ignored if not connected.
        """
        current_tai = utils.current_tai()
        lamp_commanded_on = read_lamp_set_voltage > LAMP_SET_VOLTAGE_ON_THRESHOLD
        lamp_set_power = power_from_voltage(read_lamp_set_voltage)

        on_seconds = 0
        if not self.connected:
            controller_error = LampControllerError.UNKNOWN
            controller_state = LampControllerState.UNKNOWN
            if self.get_remaining_cooldown() > 0:
                basic_state = LampBasicState.COOLDOWN
            else:
                basic_state = LampBasicState.UNKNOWN
        else:
            if self.lamp_was_on is None:
                # This is the first time set_status has been called
                # since the model was constructed.
                # If the appropriate lamp on/off time is 0 (never been set),
                # set it so that the lamp is fully warmed up or cooled down,
                # so we can immediately transition it.
                # Otherwise assume the old time is correct,
                # (even though the lamp may have been turned on or off
                # since we were last connected).
                # Note: if light_detected != lamp_commanded_on
                # then this will cause an immediate fault. That seems
                # reasonable, given the short window for this to occur,
                # and the annoyance of waiting to turn the lamp on or off.
                self.lamp_was_on = lamp_commanded_on
                if lamp_commanded_on:
                    if self.lamp_on_time == 0:
                        # Prevent unrealistic values of on_seconds
                        self.lamp_on_time = current_tai - self.config.warmup_period
            elif lamp_commanded_on:
                if not self.lamp_was_on and not self.lamp_unexpectedly_off:
                    self.lamp_was_on = True
                    self.lamp_on_time = current_tai
            else:
                if self.lamp_was_on and not self.lamp_unexpectedly_on:
                    self.lamp_was_on = False
                    self.lamp_off_time = current_tai
                    on_seconds = current_tai - self.lamp_on_time

            if self.lamp_was_on:
                if not light_detected:
                    if current_tai - self.lamp_on_time > self.config.max_lamp_on_delay:
                        # The lamp never turned on or unexpectedly turned off;
                        # either way we don't want a cooldown timer.
                        basic_state = LampBasicState.UNEXPECTEDLY_OFF
                        self.lamp_unexpectedly_off = True
                        self.lamp_was_on = False
                        self.lamp_off_time = 0
                        on_seconds = current_tai - self.lamp_on_time
                    else:
                        # Still waiting for the photo sensor
                        # to show a signal.
                        basic_state = LampBasicState.TURNING_ON
                elif self.get_remaining_warmup() > 0:
                    basic_state = LampBasicState.WARMUP
                else:
                    basic_state = LampBasicState.ON
            else:
                if light_detected:
                    if (
                        current_tai - self.lamp_off_time
                        > self.config.max_lamp_off_delay
                    ):
                        # The lamp never turned off; we don't want a cooldown
                        # timer.
                        basic_state = LampBasicState.UNEXPECTEDLY_ON
                        self.lamp_unexpectedly_on = True
                        self.lamp_off_time = 0
                    else:
                        # Still waiting for the photo sensor
                        # to stop showing a signal.
                        basic_state = LampBasicState.TURNING_OFF
                elif self.get_remaining_cooldown() > 0:
                    basic_state = LampBasicState.COOLDOWN
                else:
                    basic_state = LampBasicState.OFF

        result1 = await self.csc.evt_lampState.set_write(
            basicState=basic_state,
            controllerError=controller_error,
            controllerState=controller_state,
            lightDetected=light_detected,
            cooldownEndTime=offset_timestamp(
                self.lamp_off_time, self.config.cooldown_period
            ),
            warmupEndTime=offset_timestamp(
                self.lamp_on_time, self.config.warmup_period
            ),
            setPower=lamp_set_power,
        )

        result2 = await self.csc.evt_lampConnected.set_write(
            connected=self.labjack.connected
        )

        # Handle the command futures after reporting the state,
        # in order to make a clearer sequence: ack the command after
        # reporting the state that shows if it succeeded or failed.
        if self.connected:
            match basic_state:
                case LampBasicState.ON | LampBasicState.WARMUP:
                    if not self.lamp_on_future.done():
                        self.lamp_on_future.set_result(None)
                case LampBasicState.UNEXPECTEDLY_OFF:
                    self.abort_lamp_on_future("Lamp failed to turn on")
                case LampBasicState.OFF | LampBasicState.COOLDOWN:
                    if not self.lamp_off_future.done():
                        self.lamp_off_future.set_result(None)
                case LampBasicState.UNEXPECTEDLY_ON:
                    self.abort_lamp_off_future("Lamp failed to turn off")
        else:
            self.abort_lamp_on_future("Lost connection to the lamp controller")
            self.abort_lamp_off_future("Lost connection to the lamp controller")

        # Turn off the lamp controller if the bulb is unexpectedly off.
        if self.lamp_unexpectedly_off and self.connected:
            await self._set_lamp_power(0)

        if on_seconds > 0:
            await self.csc.evt_lampOnHours.set_write(hours=on_seconds / 3600)

        if result1.did_change or result2.did_change:
            await self.call_status_callback()

    def get_remaining_cooldown(self, tai=None):
        """Return the remaining cooldown duration (seconds), or 0 if none.

        Return 0 if the lamp is unexpectedly off. That means the lamp never
        turned on, or burned out, and either way, there is no point to
        a cooldown period.

        Parameters
        ----------
        tai : `float` or `None`, optional
            TAI time (unix seconds).
        """
        if self.lamp_off_time == 0:
            return 0
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
        if self.lamp_on_time == 0:
            return 0
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
        if self.csc.evt_shutterState.has_data:
            if (
                self.csc.evt_shutterState.data.commandedState == desired_state
                and self.csc.evt_shutterState.data.actualState == desired_state
            ):
                # Already done
                return
            if self.csc.evt_shutterState.data.actualState == ShutterState.INVALID:
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
        await self.csc.evt_shutterState.set_write(
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
            await self.csc.evt_shutterState.set_write(enabled=False)

        if self.csc.evt_shutterState.data.actualState == ShutterState.INVALID:
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
            If the lamp is already in the process of being turned on,
            or if the lamp is off but still cooling down.
        """
        if not self.lamp_on_future.done():
            # Note: we cannot simply wait for the existing task to finish,
            # because the new power may not match the old one.
            raise salobj.ExpectedError("Already turning the lamp on.")
        if power < MIN_POWER or power > MAX_POWER:
            raise salobj.ExpectedError(
                f"{power} must be in range [{MIN_POWER}, {MAX_POWER}], inclusive"
            )
        remaining_cooldown = self.get_remaining_cooldown()
        if remaining_cooldown > 0:
            raise salobj.ExpectedError(
                f"Cooling; wait {remaining_cooldown:0.1f} seconds."
            )

        self.lamp_unexpectedly_on = False
        self.abort_lamp_off_future("Superseded by a turnLampOn command")
        # Note: if the lamp is already on, then waiting is not strictly
        # necessary, but it only causes a very minor delay.
        self.lamp_on_future = asyncio.Future()
        await self._set_lamp_power(power)
        await asyncio.wait_for(
            self.lamp_on_future,
            timeout=self.config.max_lamp_on_delay + ONOFF_COMMAND_TIMEOUT_MARGIN,
        )

    async def turn_lamp_off(self, force, wait, reason):
        """Turn the lamp off (if on). Fail if warming up, unless force=True.

        Parameters
        ----------
        force : `bool`
            Force the lamp off, even if warming up.
            This can significantly reduce bulb life.
        wait : `bool`
            Wait for the lamp to turn off?
        reason : `str`
            Why is the lamp being turned off? Used as the full text of the
            lamp_on_future exception, if aborting turning on the lamp.

        Raises
        ------
        salobj.ExpectedError
            If warming up and force=False.
        """
        if not self.lamp_was_on:
            return
        if not self.lamp_off_future.done():
            # The lamp is already being turned off. Wait for it to finish.
            await self.lamp_off_future
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

        self.lamp_unexpectedly_off = False
        self.abort_lamp_on_future(reason)
        self.lamp_off_future = asyncio.Future()
        await self._set_lamp_power(0)
        if wait:
            await asyncio.wait_for(
                self.lamp_off_future,
                timeout=self.config.max_lamp_off_delay + ONOFF_COMMAND_TIMEOUT_MARGIN,
            )

    async def _set_lamp_power(self, power):
        """Set the desired lamp power.

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
        async with self.change_power_lock:
            await self.labjack.write(lamp_set_voltage=voltage)
            await asyncio.sleep(READ_POWER_DELAY)

    async def call_status_callback(self):
        """Call the status callback, if there is one."""
        if self.status_callback is None:
            return
        try:
            await self.status_callback(self)
        except Exception:
            self.log.exception("status callback failed")
