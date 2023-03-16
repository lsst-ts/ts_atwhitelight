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
    "ERROR_BLINKING_DURATION",
    "STATUS_INTERVAL",
    "MIN_POWER",
    "MAX_POWER",
    "SHUTTER_ENABLE",
    "SHUTTER_DISABLE",
    "SHUTTER_OPEN",
    "SHUTTER_CLOSE",
    "LabJackChannels",
    "VOLTS_AT_MIN_POWER",
    "VOLTS_AT_MAX_POWER",
    "VOLTS_PER_WATT",
    "voltage_from_power",
]

from lsst.ts import salobj

# How long after a lamp turns off before we are sure it's done blinking (sec)
ERROR_BLINKING_DURATION = 1

# Interval between reading state (seconds).
# Must be short enough to reliably follow the blinking error signal
# (e.g. < ERROR_BLINKING_DURATION / 4 or so).
# Keeping it short also reduces latency in detecting changes.
STATUS_INTERVAL = 0.15

# Constants to keep track of the sign of LabJack binary output signals
SHUTTER_ENABLE = 0
SHUTTER_DISABLE = 1

SHUTTER_OPEN = 0
SHUTTER_CLOSE = 1


class LabJackChannels:
    """Static configuration for LabJack connected to KiloArc lamp controller.

    All inputs are 1 if active/on.

    Outputs use the ``SHUTTER_x`` constants above.
    """

    read = dict(
        photosensor="AIN0",
        blinking_error="FIO4",
        cooldown="FIO5",
        standby_or_on="FIO6",
        error_exists="FIO7",
        shutter_open="EIO4",
        shutter_closed="EIO6",
    )
    write = dict(
        set_power="DAC0",
        shutter_enable="EIO3",  # 0=enable
        shutter_direction="EIO2",  # 0=open
    )


# KiloArc parameters for the voltage input that sets lamp power
MIN_POWER = 800
MAX_POWER = 1200
VOLTS_AT_MIN_POWER = 1.961
VOLTS_AT_MAX_POWER = 5
VOLTS_PER_WATT = (VOLTS_AT_MAX_POWER - VOLTS_AT_MIN_POWER) / (MAX_POWER - MIN_POWER)


def voltage_from_power(power):
    """Compute voltage to provide to the lamp power input of the KiloArc
    lamp controller.

    Note that the KiloArc quantizes power to in 2.3W steps.

    Parameters
    ----------
    power : `float`
        Desired lamp power (W)

    Returns
    -------
    voltage : `float`
        The voltage to provide to the lamp power input of the KiloArc
        lamp controller.

    Raises
    ------
    lsst.ts.salobj.ExpectedError
        If power is not 0 and is not between 800 and 1200W (inclusive).
    """
    if power == 0:
        return 0

    if power < MIN_POWER or power > MAX_POWER:
        raise salobj.ExpectedError(
            f"{power} must be in range [{MIN_POWER}, {MAX_POWER}], inclusive"
        )
    return (power - MIN_POWER) * VOLTS_PER_WATT + VOLTS_AT_MIN_POWER
