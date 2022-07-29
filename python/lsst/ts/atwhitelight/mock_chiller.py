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

__all__ = ["MockChiller"]

import asyncio
import functools

from lsst.ts import tcpip
from lsst.ts import utils
from .chiller_client import ChillerClient
from .chiller_base import (
    ChillerControlSensor,
    format_chiller_command_value,
)
from lsst.ts.idl.enums.ATWhiteLight import ChillerControllerState


class MockChiller(tcpip.OneClientServer):
    """Mock the ThermoTek T257P TCP/IP interface."""

    def __init__(self, log):
        self.command_task = utils.make_done_future()

        # dict of cmd_id: async handler
        # each handler accepts the command data as a string
        # and returns the data portion of the reply as a string
        self.command_handlers = {
            "01": self.handle_watchdog,
            "03": self.handle_read_control_temperature,
            "04": functools.partial(
                self.handle_read_temperature, attr_name="supply_temperature"
            ),
            "07": functools.partial(
                self.handle_read_temperature, attr_name="return_temperature"
            ),
            "08": functools.partial(
                self.handle_read_temperature, attr_name="ambient_temperature"
            ),
            "09": self.handle_read_coolant_flow_rate,
            "10": functools.partial(self.handle_read_tec_bank_current, bank=1),
            "11": functools.partial(self.handle_read_tec_bank_current, bank=2),
            "13": self.handle_read_tec_drive_level,
            "15": self.handle_set_chiller_status,
            "16": self.handle_set_control_sensor,
            "17": self.handle_set_control_temperature,
            "18": self.handle_read_l1_alarms,
            "19": self.handle_read_l2_alarms,
            "20": self.handle_read_warnings,
            "49": self.handle_read_uptime,
            "50": functools.partial(self.handle_read_fan_speed, fan_num=1),
            "51": functools.partial(self.handle_read_fan_speed, fan_num=2),
            "52": functools.partial(self.handle_read_fan_speed, fan_num=3),
            "53": functools.partial(self.handle_read_fan_speed, fan_num=4),
        }

        # Users may change these attributes
        # to affect the reply to various query commands
        self.l1_alarms = 0
        self.l21_alarms = 0
        self.l22_alarms = 0
        self.warnings = 0
        # Temperatures in C. reported rounded to 0.1
        self.ambient_temperature = 31.1
        self.return_temperature = 29.2
        self.supply_temperature = 28.4
        self.coolant_flow_rate = 1.9
        # Fan speeds in rev/second; reported rounded to 1
        self.fan_speeds = [11, 22, 33, 44]
        # TEC bank currents in amperes; reported rounded to 0.001
        self.tec_bank_currents = [1.123, -2.234]
        # TEC drive level in %; reported rounded to 1
        self.tec_drive_level = 67
        self.is_cooling = True

        self.uptime_minutes = 456

        # Our chiller only supports ChillerControlSensor.SUPPLY
        # and rejects attempts to change it.
        self.control_sensor = ChillerControlSensor.SUPPLY

        # These values are managed by commands
        self.controller_state = ChillerControllerState.STANDBY
        self.pump_running = False
        self.demand_temperature = 20  # arbitrary reasonable initial value

        super().__init__(
            name="MockChiller",
            host=tcpip.LOCAL_HOST,
            port=0,
            log=log,
            connect_callback=self.connect_callback,
        )

    def connect_callback(self, server):
        self.command_task.cancel()
        if self.connected:
            self.command_task = asyncio.create_task(self.command_loop())

    async def command_loop(self):
        """Read and execute commands."""
        self.log.info("command_loop begins")
        try:
            while self.connected:
                command_bytes = await self.reader.readuntil(b"\r")
                # trim the checksum and \r
                command = command_bytes.decode()[:-3]
                cmd_id = command[3:5]
                command_data = command[13:]
                reply_body = f"#{command[1:5]}0{command[5:13]}"
                handler = self.command_handlers.get(cmd_id)
                if handler is not None:
                    data = await handler(command_data)
                else:
                    # echo command
                    data = command_data
                reply = reply_body + data
                reply = reply_body + data
                checksum = ChillerClient.compute_checksum(reply)
                encoded_reply = f"{reply}{checksum}\r".encode()
                self.writer.write(encoded_reply)
        except asyncio.CancelledError:
            self.log.info("command_loop ends")
            raise
        except (ConnectionError, asyncio.IncompleteReadError):
            self.log.error("Socket closed")
            asyncio.create_task(self.close_client())
        except Exception:
            self.log.exception("command_loop failed")
            asyncio.create_task(self.close_client())

        self.log.info("command_loop ends")

    def format_mask(self, value, ndig, name):
        """Format a hex mask return data, e.g. alarms and warnings.

        Note that the string is in reverse order, e.g.
        value=0x12, ndig=4 is returned as "2100".
        See note in `lsst.ts.idl.enums.ATWhiteLight.ChillerL1Alarms`
        for the reason.
        """
        ret = f"{value:0{ndig}X}"[::-1]
        if len(ret) > ndig:
            self.log.warning(f"truncating {name}={ret} to {ndig} chars; value={value}")
        return ret

    async def handle_read_control_temperature(self, data):
        return format_chiller_command_value(
            self.demand_temperature, scale=10, nchar=5, signed=True
        )

    async def handle_read_fan_speed(self, data, fan_num):
        if fan_num not in (1, 2, 3, 4):
            raise RuntimeError(f"fan_num={fan_num!r} must be one of 1, 2, 3, 4")
        value = self.fan_speeds[fan_num - 1]
        return format_chiller_command_value(value, scale=1, nchar=4, signed=False)

    async def handle_read_coolant_flow_rate(self, data):
        if self.coolant_flow_rate < 0:
            raise RuntimeError(
                f"coolant_flow_rate={self.coolant_flow_rate} must not be negative"
            )
        return format_chiller_command_value(
            self.coolant_flow_rate, scale=10, nchar=5, signed=True
        )

    async def handle_read_l1_alarms(self, data):
        return self.format_mask(value=self.l1_alarms, ndig=6, name="l1_alarms")

    async def handle_read_l2_alarms(self, data):
        if data == "1":
            value = self.l21_alarms
        elif data == "2":
            value = self.l22_alarms
        else:
            raise RuntimeError("Invalid data for reading L2 alarms")
        return data + self.format_mask(value=value, ndig=8, name="l21_alarms")

    async def handle_read_tec_bank_current(self, data, bank):
        if bank not in (1, 2):
            raise RuntimeError(f"bank={bank!r} must be one of 1, 2")
        value = self.tec_bank_currents[bank - 1]
        return format_chiller_command_value(value, scale=1000, nchar=5, signed=True)

    async def handle_read_tec_drive_level(self, data):
        numstr = format_chiller_command_value(
            value=self.tec_drive_level, scale=1, nchar=3, signed=False
        )
        mode_str = "C" if self.is_cooling else "H"
        return f"{numstr},{mode_str}"

    async def handle_read_temperature(self, data, attr_name):
        value = getattr(self, attr_name)
        return format_chiller_command_value(value, scale=10, nchar=5, signed=True)

    async def handle_read_uptime(self, data):
        return format_chiller_command_value(
            value=self.uptime_minutes, scale=1, nchar=6, signed=False
        )

    async def handle_read_warnings(self, data):
        return self.format_mask(value=self.warnings, ndig=8, name="l21_alarms")

    async def handle_set_chiller_status(self, data):
        if data == "0":
            self.controller_state = ChillerControllerState.STANDBY
            self.pump_running = False
        elif data == "1":
            self.controller_state = ChillerControllerState.RUN
            self.pump_running = True
        else:
            self.log.warning(
                f"Unrecognized chiller state: {data}; leaving state unchanged"
            )

        return data

    async def handle_set_control_sensor(self, data):
        self.control_sensor = ChillerControlSensor(int(data))
        return data

    async def handle_set_control_temperature(self, data):
        # The value is specified in C * 10 (rounded to the nearest int)
        # as per `ChillerCommandFormatter.format_command`
        self.demand_temperature = float(data) / 10
        return data

    async def handle_watchdog(self, data):
        """Handle the watchdog command; return data"""
        alarms_present = (
            self.l1_alarms != 0 or self.l21_alarms != 0 or self.l22_alarms != 0
        )
        warnings_present = self.warnings != 0
        return (
            f"{int(self.controller_state)}{int(self.pump_running)}"
            f"{int(alarms_present)}{int(warnings_present)}"
        )
