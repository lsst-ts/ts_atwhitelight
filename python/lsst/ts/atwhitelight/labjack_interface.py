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
import functools
import socket
import types

# Hide my error `Module "labjack" has no attribute "ljm"`
from labjack import ljm  # type: ignore

from .lamp_base import LabJackChannels

# Time limit for connecting to the LabJack (seconds)
CONNECT_TIMEOUT = 5

# Time limit for communicating with the LabJack (seconds)
READ_WRITE_TIMEOUT = 5

# LabJack's special identifier to run in simulation mode.
MOCK_IDENTIFIER = "LJM_DEMO_MODE"


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

        # handle to LabJack device
        self.handle = None

        # The thread pool executor used by `_run_in_thread`.
        self._thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

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

    async def read(self):
        """Read all channels specified in LabjackChannels.read.

        Returns
        -------
        data : `types.SimpleNamespace`
            Struct of label=value, where label is a key in LabjackChannels.read
        """
        channels = list(LabJackChannels.read.values())
        try:
            values = await self._run_in_thread(
                func=self._blocking_read,
                channels=channels,
                timeout=READ_WRITE_TIMEOUT,
            )
        except Exception as e:
            self.log.error(
                f"Read channels={channels!r} from LabJack handle={self.handle!r} "
                f"failed: {e!r}"
            )
            raise
        if len(values) != len(LabJackChannels.read):
            raise RuntimeError(
                f"The number of read values {values} does not match the number of channels {channels}"
            )
        channel_dict = {
            label: value for label, value in zip(LabJackChannels.read.keys(), values)
        }
        return types.SimpleNamespace(**channel_dict)

    async def write(self, **kwargs):
        """Write to one or more labelled channels.

        Parameters
        ----------
        kwargs : `dict`
            Dict of label: value, where label is a key in LabJackChannels.write
        """
        bad_labels = kwargs.keys() - LabJackChannels.write.keys()
        if bad_labels:
            raise ValueError(f"Unrecognized labels={sorted(bad_labels)}")
        try:
            channel_dict = {
                LabJackChannels.write[label]: value for label, value in kwargs.items()
            }
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
