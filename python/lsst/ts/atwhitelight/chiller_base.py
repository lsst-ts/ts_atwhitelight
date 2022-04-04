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
    "ChillerControlSensor",
    "ChillerThresholdType",
    "format_chiller_command_value",
]

import enum


class ChillerControlSensor(enum.IntEnum):
    """Which sensor to use for the temperature control loop."""

    SUPPLY = 0
    RETURN = enum.auto()
    EXTERNAL_RTD = enum.auto()
    EXTERNAL_THERMISTOR = enum.auto()


class ChillerThresholdType(enum.Enum):
    """Type of threshold for setting warning and alarm thresholds."""

    HighSupplyTemperature = 0
    LowSupplyTemperature = enum.auto()
    HighAmbientTemperature = enum.auto()
    LowAmbientTemperature = enum.auto()
    LowCoolantFlowRate = enum.auto()


def format_chiller_command_value(value, scale, nchar, signed):
    """Format a value as the string needed for a chiller command.

    Parameters
    ----------
    value : `float`
        Value to be formatted
    scale : `float`
        The amount by which to multiply the value before
        formatting as a string with no decimal point:

        * 10: temperature (C) and flow rate (liters per minute)
        * 1000: TEC current (amps)
    nchar : `int`
        The number of characters in the string.
    signed : `boolean`
        Should the value include a leading sign?
        If false then negative values are rejected.

    Returns
    -------
    formatted_value : `str`
        Formatted value; a 5 character string {sign}{dddd}, where:

        * sign is "+" or "-"
        * dddd is abs(value) * scale rounded to the nearest integer

        For example:

        * value=1.29, scale=10 is formatted as "+0013"
        * value=-0.2012, scale=1000 is formatted as "-0201"
    """
    if not signed and value < 0:
        raise ValueError(f"value={value} < 0 but signed=False")
    sign_char = "+" if signed else ""
    formatted_value = f"{value*scale:{sign_char}0{nchar}.0f}"
    if len(formatted_value) > nchar:
        raise ValueError(
            f"value={value} out of range with scale={scale}, nchar={nchar}"
        )
    return formatted_value
