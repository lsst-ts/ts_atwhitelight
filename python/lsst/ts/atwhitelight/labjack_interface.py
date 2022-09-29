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

__all__ = [
    "LabJackInterface",
]

import asyncio
import concurrent
import dataclasses
import functools
import socket

from lsst.ts import utils

from .lamp_base import (
    LabJackChannels,
    SHUTTER_ENABLE,
    SHUTTER_DISABLE,
    SHUTTER_OPEN,
    SHUTTER_CLOSE,
    VOLTS_AT_MIN_POWER,
    VOLTS_AT_MAX_POWER,
)

# Hide my error `Module "labjack" has no attribute "ljm"`
from labjack import ljm  # type: ignore

# Time limit for connecting to the LabJack (seconds)
CONNECT_TIMEOUT = 5

# Time limit for communicating with the LabJack (seconds)
READ_WRITE_TIMEOUT = 5

# LabJack's special identifier to run in simulation mode.
MOCK_IDENTIFIER = "LJM_DEMO_MODE"

# Duration of lamp controller's cooldown timer (seconds).
# This should be shorter than the CSC's config.lamp.cooldown_duration
# in order to be realistic.
COOLDOWN_DURATION = 4


@dataclasses.dataclass
class MockedReadValues:
    """Read values that we simulate"""

    blinking_error: int = 0
    cooldown: int = 0
    standby_or_on: int = 0
    error_exists: int = 0
    shutter_open: int = 0
    shutter_closed: int = 1


class LabJackInterface:
    """Communicate with a LabJack T4, or T7.

    Parameters
    ----------
    identifier : `str`
        LabJack indentifier:

        * An IP address if connection_type=TCP
        * A serial number if connection_type = USB
        * For testing in an environment with only one LabJack you may use ANY.
    device_type : `str`
        LabJack model
    connection_type : `str`
        Connection type
    simulate : `int`, optional
        Use a simulated LabJack?

    Notes
    -----
    In simulation mode the mock LabJack returns unspecified values,
    and those values may change in future versions of the LabJack software.
    """

    def __init__(
        self,
        identifier,
        log,
        device_type="T4",
        connection_type="TCP",
        simulate=False,
    ):
        self.identifier = identifier
        self.log = log.getChild("LabJackInterface")
        self.device_type = device_type
        self.connection_type = connection_type
        self.simulate = simulate

        # Time to open or close the shutter (seconds)
        self.shutter_duration = 1

        self.cooldown_duration = COOLDOWN_DURATION

        self.do_open_shutter = False
        self.shutter_open_switch = False
        self.shutter_closed_switch = True
        self.shutter_enabled = False
        self.lamp_on = False
        self.lamp_off_time = 0

        self.move_shutter_task = utils.make_done_future()

        # handle to LabJack device
        self.handle = None

        # The thread pool executor used by `_run_in_thread`.
        self._thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        # Read constants
        self.read_constants = dict(
            error_exists=0,
            blinking_error=0,
        )

        self.mocked_read_values = MockedReadValues()

    @property
    def connected(self):
        return self.handle is not None

    async def connect(self):
        """Connect to the LabJack and check we can read the specified channels.

        Disconnect first, if connected.
        """
        self.log.info(
            f"Connect to LabJack {self.device_type}, "
            f"config.identifier={self.identifier!r}, "
            f"config.connection_type={self.connection_type}"
        )
        try:
            await self._run_in_thread(
                func=self._blocking_connect, timeout=CONNECT_TIMEOUT
            )
        except Exception as e:
            self.log.error(f"Could not connect to LabJack: {e!r}")
            raise

    async def disconnect(self):
        """Disconnect from the LabJack. A no-op if disconnected."""
        try:
            await self._run_in_thread(
                func=self._blocking_disconnect, timeout=CONNECT_TIMEOUT
            )
        finally:
            self.handle = None

    async def move_shutter(self):
        if self.do_open_shutter:
            self.shutter_closed_switch = False
            if not self.shutter_open_switch:
                await asyncio.sleep(self.shutter_duration)
                self.shutter_open_switch = True
        else:
            self.shutter_open_switch = False
            if not self.shutter_closed_switch:
                await asyncio.sleep(self.shutter_duration)
                self.shutter_closed_switch = True

    async def read(self):
        """Read all channels specified in LabjackChannels.read.

        Returns
        -------
        data : `types.SimpleNamespace`
            Struct of label=value, where label is a key in LabjackChannels.read
        """
        # All read data is simulated
        self.mocked_read_values.standby_or_on = False
        self.mocked_read_values.cooldown = False
        if not self.lamp_on:
            off_duration = utils.current_tai() - self.lamp_off_time
            if off_duration > self.cooldown_duration:
                self.mocked_read_values.standby_or_on = True
            else:
                self.mocked_read_values.cooldown = True
        else:
            self.mocked_read_values.standby_or_on = True
        self.mocked_read_values.shutter_open = self.shutter_open_switch
        self.mocked_read_values.shutter_closed = self.shutter_closed_switch
        return self.mocked_read_values

    async def write(self, **kwargs):
        """Write to one or more labelled channels.

        Parameters
        ----------
        kwargs : `dict`
            Dict of label: value, where label is a key in LabJackChannels.write
        """
        # The only data to write is `set_power`;
        # parse the others to mock the appropriate behavior.
        bad_labels = kwargs.keys() - LabJackChannels.write.keys()
        if bad_labels:
            raise ValueError(f"Unrecognized labels={sorted(bad_labels)}")

        # Translate set_power label from a power to 0/1,
        # because the hack drives a digital output, not an analog output.
        # Fail if set_power out of range.
        # Turn on the lamp if set_power > 0
        # Turn off the lamp otherwise
        set_power = kwargs.get("set_power", None)
        if set_power is not None:
            lamp_on = True
            if set_power == 0:
                lamp_on = False
                self.lamp_off_time = utils.current_tai()
            elif set_power < VOLTS_AT_MIN_POWER or set_power > VOLTS_AT_MAX_POWER:
                raise RuntimeError(
                    f"Invalid set_power={set_power} must be 0 or in range "
                    f"[{VOLTS_AT_MIN_POWER}, {VOLTS_AT_MAX_POWER}] V"
                )
            try:
                channel_dict = {LabJackChannels.write["set_power"]: lamp_on}
                await self._run_in_thread(
                    self._blocking_write,
                    channel_dict=channel_dict,
                    timeout=READ_WRITE_TIMEOUT,
                )
            except Exception as e:
                self.log.error(
                    f"Write channel_dict={channel_dict!r} "
                    f"to LabJack handle={self.handle!r} failed: {e!r}"
                )
                raise
            self.lamp_on = lamp_on

        shutter_direction = kwargs.get("shutter_direction")
        if shutter_direction is not None:
            self.do_open_shutter = {SHUTTER_OPEN: True, SHUTTER_CLOSE: False}[
                shutter_direction
            ]

        shutter_enable = kwargs.get("shutter_enable")
        if shutter_enable is not None:
            self.move_shutter_task.cancel()
            self.shutter_enabled = shutter_enable
            do_enable_shutter = {SHUTTER_ENABLE: True, SHUTTER_DISABLE: False}[
                shutter_enable
            ]
            if do_enable_shutter:
                self.move_shutter_task = asyncio.create_task(self.move_shutter())

    async def _run_in_thread(self, func, timeout, **kwargs):
        """Run a blocking function in a thread pool executor.

        Only one function will run at a time, because all calls use the same
        thread pool executor, which only has a single thread.

        Parameters
        ----------
        func : `Callable`
            The blocking function to run.
        timeout : `float`
            Time limit (seconds).
        **kwargs :
            Keyword arguments for the function.
        """
        loop = asyncio.get_running_loop()
        curried_func = functools.partial(func, **kwargs)
        return await asyncio.wait_for(
            loop.run_in_executor(self._thread_pool, curried_func), timeout=timeout
        )

    def _blocking_connect(self) -> None:
        """Connect to the LabJack.

        Disconnect first, if connected.

        Call in a thread to avoid blocking the event loop.
        """
        if self.handle is not None:
            self.log.warning("Already connected; disconnecting and reconnecting")
            self._blocking_disconnect()

        if self.simulate:
            identifier = MOCK_IDENTIFIER
            self.log.info(f"simulation mode, so identifier changed to {identifier!r}")
        else:
            identifier = self.identifier
            if self.connection_type in {"TCP", "WIFI"}:
                # Resolve domain name, since ljm does not do this
                identifier = socket.gethostbyname(identifier)
                self.log.info(f"resolved identifier={identifier!r}")

        self.handle = ljm.openS(self.device_type, self.connection_type, identifier)

    def _blocking_disconnect(self):
        """Disconnect from the LabJack. A no-op if disconnected.

        Call in a thread to avoid blocking the event loop.
        """
        if self.handle is not None:
            try:
                ljm.close(self.handle)
            finally:
                self.handle = None

    def _blocking_read(self, channels):
        """Read data from the LabJack. This can block.

        Call in a thread to avoid blocking the event loop.

        Parameters
        ----------
        channels : `list`
            List of channel names

        Returns
        -------
        values : `list`
            The read data, as a list of values.
        """
        if self.handle is None:
            raise RuntimeError("Not connected")

        num_frames = len(channels)
        return ljm.eReadNames(self.handle, num_frames, channels)

    def _blocking_write(self, channel_dict):
        """Write data from the LabJack. This can block.

        Call in a thread to avoid blocking the event loop.

        Parameters
        ----------
        channel_dict : `Dict` [`str`, `float`]
            The data to write, as a dict of channel_name: value.

        Raises
        ------
        RuntimeError
            If not connected or the write fails.
        """
        if self.handle is None:
            raise RuntimeError("Not connected")

        num_frames = len(channel_dict)
        channels = list(channel_dict.keys())
        values = list(channel_dict.values())
        ljm.eWriteNames(self.handle, num_frames, channels, values)
