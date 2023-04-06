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

__all__ = ["ChillerClient"]

import asyncio

from lsst.ts import tcpip


class ChillerClient(tcpip.Client):
    """TCP/IP client for the chiller.

    Parameters
    ----------
    device_id : `str`
        Device ID of the chiller. Typically "01".
    host : `str`
        TCP/IP host address of the chiller.
    port : `int`
        TCP/IP port number of the chiller.
    log : `logging.Logger`
        Logger.

    Attributes
    ----------
    reader : `asyncio.StreamReader` or `None`
        Stream reader. If None then not connected.
    writer : `asyncio.StreamWriter` or `None`
        Stream writer. If None then not connected.
    """

    def __init__(self, device_id, host, port, log):
        self.device_id = device_id
        self.communication_lock = asyncio.Lock()
        super().__init__(host=host, port=port, log=log, name="ChillerClient")

    async def run_command(self, cmd):
        """Send a command and wait for the reply.

        Parameters
        ----------
        cmd : `str`
            Command, with no device ID or checksum.

        Returns
        -------
        reply : `str`
            The reply, without the trailing checksum and \r.
        """
        if not self.connected:
            raise ConnectionError("not connected")

        full_cmd = self.format_full_command(cmd).encode("ascii")

        async with self.communication_lock:
            self.log.debug(f"Run chiller command {full_cmd}")
            await self.write(full_cmd)
            reply = await self.readuntil(separator=b"\r")
        self.log.debug(f"Read chiller reply {reply}")
        return reply.decode()[:-3]

    def format_full_command(self, cmd):
        r"""Generate a full command with device ID and checksum.

        Format a command as ".{self.device_id}{cmd}(checksum}\r"
        where checksum is for everything that comes before.

        Parameters
        ----------
        cmd : `str`
            Command as string of 10-18 ASCII characters:
            the command ID followed by 8 chars of
            descriptive text and 0-8 characters of
            data payload.

        Returns
        -------
        result : `str`
            Full command string.
        """
        if len(cmd) < 10 or len(cmd) > 18:
            raise ValueError(f"{cmd} must be between 10 and 18 chars long")

        start = f".{self.device_id}{cmd}"
        checksum = self.compute_checksum(start)
        return f"{start}{checksum}\r"

    @staticmethod
    def compute_checksum(st):
        """
        Compute a checksum field as two ASCII hexadecimal bytes
        representing the sum of all previous bytes (8 bit
        summation, no carry) of the command starting with SOC

        Parameters
        ----------
        st : `str`
            ASCII string to be checksummed

        Returns
        -------
        checksum : str
            2-character ASCII string

        Raises
        ------
        UnicodeEncodeError
            If st contains any non-ASCII characters.
        """
        # Check that the string is pure ASCII
        st.encode("ascii", errors="strict")
        # Compute the checksum
        total = sum(ord(ch) for ch in st)
        return hex(total)[-2:]
