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

import unittest

import numpy as np
import pytest
from lsst.ts import atwhitelight, salobj


class LampBaseTestCase(unittest.TestCase):
    def test_voltage_from_power_and_power_from_voltage(self):
        # Test special values
        assert atwhitelight.voltage_from_power(0) == 0

        assert atwhitelight.VOLTS_AT_MIN_POWER == pytest.approx(
            atwhitelight.voltage_from_power(atwhitelight.MIN_POWER)
        )
        assert atwhitelight.VOLTS_AT_MAX_POWER == pytest.approx(
            atwhitelight.voltage_from_power(atwhitelight.MAX_POWER)
        )

        # Test round trip for in-range values
        for power in np.linspace(
            start=atwhitelight.MIN_POWER,
            stop=atwhitelight.MAX_POWER,
            num=10,
            endpoint=True,
            dtype=float,
        ):
            with self.subTest(power=power):
                voltage = atwhitelight.voltage_from_power(power)
                round_trip_power = atwhitelight.power_from_voltage(voltage)
                assert power == pytest.approx(round_trip_power)

        # Test out of range values power
        margin = 0.001
        for bad_power in np.linspace(
            start=margin,
            stop=atwhitelight.MIN_POWER - margin,
            endpoint=True,
            dtype=float,
        ):
            with self.subTest(bad_power=bad_power):
                with pytest.raises(salobj.ExpectedError):
                    atwhitelight.voltage_from_power(bad_power)
        with pytest.raises(salobj.ExpectedError):
            atwhitelight.voltage_from_power(atwhitelight.MAX_POWER + margin)

        # Test out of range voltage; use atol slightly smaller than margin
        # to provide safety from roundoff error.
        for bad_voltage in np.linspace(
            start=margin, stop=atwhitelight.VOLTS_AT_MIN_POWER - margin
        ):
            with self.subTest(bad_voltage=bad_voltage):
                with pytest.raises(salobj.ExpectedError):
                    atwhitelight.power_from_voltage(bad_voltage, atol=margin * 0.999)
        with pytest.raises(salobj.ExpectedError):
            atwhitelight.power_from_voltage(
                atwhitelight.VOLTS_AT_MAX_POWER + margin, atol=margin * 0.999
            )
