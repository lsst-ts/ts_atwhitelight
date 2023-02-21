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

__all__ = ["MockLabJackInterface"]

import asyncio

from lsst.ts import utils
from lsst.ts.idl.enums.ATWhiteLight import LampControllerError

from .labjack_interface import LabJackInterface
from .lamp_base import (
    SHUTTER_CLOSE,
    SHUTTER_DISABLE,
    SHUTTER_ENABLE,
    SHUTTER_OPEN,
    VOLTS_AT_MAX_POWER,
    VOLTS_AT_MIN_POWER,
)

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


class MockLabJackInterface(LabJackInterface):
    """Mock version of LabJackInterface.

    This mock monitors what data is written to the LabJack and adjusts
    what data is read to be what we expect from the real lamp controller.

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
    This mock LabJack starts up in the following state:

    * Lamp is off and fully cooled down
    * Lamp controller is reporting an error
    * The shutter is closed and disabled
    """

    def __init__(
        self,
        identifier,
        log,
        device_type="T4",
        connection_type="TCP",
        simulate=False,
    ):
        if not simulate:
            raise ValueError("simulate must be true")

        self.set_power = 0

        # Time to open or close the shutter (seconds)
        self.shutter_duration = 1

        self.cooldown_duration = COOLDOWN_DURATION

        self.do_open_shutter = False
        self.shutter_open_switch = False
        self.shutter_closed_switch = True
        self.shutter_enabled = False
        self.blinking_error = False
        self.lamp_off_time = 0

        self.blinking_error_task = utils.make_done_future()
        self.move_shutter_task = utils.make_done_future()
        self.controller_error = LampControllerError.NONE
        super().__init__(
            identifier=identifier,
            log=log,
            device_type=device_type,
            connection_type=connection_type,
            simulate=simulate,
        )

    async def read(self):
        data = await super().read()

        for name in ("standby_or_on", "cooldown"):
            setattr(data, name, False)
        if self.set_power == 0:
            off_duration = utils.current_tai() - self.lamp_off_time
            if off_duration > self.cooldown_duration:
                data.standby_or_on = True
            else:
                data.cooldown = True
        else:
            data.standby_or_on = True
        data.error_exists = int(self.controller_error != LampControllerError.NONE)
        data.blinking_error = self.blinking_error
        data.shutter_open = self.shutter_open_switch
        data.shutter_closed = self.shutter_closed_switch
        return data

    async def write(self, **kwargs):
        await super().write(**kwargs)

        # The lamp controller power signal reads a voltage of
        # 5V for 1200W down to 1.961 for 800W, or 0 for off.
        set_power = kwargs.get("set_power", None)
        if set_power is not None:
            if set_power == 0:
                if self.set_power > 0:
                    self.lamp_off_time = utils.current_tai()
            elif set_power < VOLTS_AT_MIN_POWER or set_power > VOLTS_AT_MAX_POWER:
                raise RuntimeError(
                    f"Invalid set_power={set_power} must be 0 or in range "
                    f"[{VOLTS_AT_MIN_POWER}, {VOLTS_AT_MAX_POWER}] V"
                )
            self.set_power = set_power

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

    async def blinking_error_loop(self):
        try:
            while self.controller_error > 0:
                num_flashes = int(self.controller_error)
                for _ in range(num_flashes):
                    self.blinking_error = True
                    await asyncio.sleep(0.5)
                    self.blinking_error = False
                    await asyncio.sleep(0.5)
                await asyncio.sleep(1.0)
        except Exception as e:
            self.log.error(f"blinking error loop failed: {e!r}")
            raise

    def set_error(self, controller_error):
        if controller_error == 0:
            # -1 for no error, >0 for a specific error;
            # 0 is unknown and we can't blink 0 times
            raise ValueError(
                "controller_error must not be LampControllerError.UNKNOWN=0; "
                "use LampControllerError.NONE=-1 for no error "
                "or a positive value for a known error"
            )
        self.blinking_error_task.cancel()
        self.controller_error = controller_error
        if self.controller_error > 0:
            self.blinking_error_task = asyncio.create_task(self.blinking_error_loop())
