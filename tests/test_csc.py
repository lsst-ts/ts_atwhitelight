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

import asyncio
import math
import pathlib
import unittest

import pytest
from lsst.ts import atwhitelight, salobj
from lsst.ts.atwhitelight import ErrorCode
from lsst.ts.atwhitelight.chiller_model import READ_RETURN_TEMPERATURE
from lsst.ts.idl.enums.ATWhiteLight import (
    ChillerControllerState,
    LampBasicState,
    LampControllerError,
    LampControllerState,
    ShutterState,
)
from lsst.ts.utils import current_tai

STD_TIMEOUT = 30  # standard command timeout (sec)
TEST_CONFIG_DIR = pathlib.Path(__file__).parents[1].joinpath("tests", "data", "config")

# Amount by which the clock may jitter when running Docker on macOS
TIME_SLOP = 0.2


class CscTestCase(salobj.BaseCscTestCase, unittest.IsolatedAsyncioTestCase):
    def basic_make_csc(self, initial_state, config_dir, simulation_mode, override=""):
        return atwhitelight.ATWhiteLightCsc(
            config_dir=config_dir,
            initial_state=initial_state,
            override=override,
            simulation_mode=simulation_mode,
        )

    async def check_fault_to_standby_while_cooling(self, can_recover):
        """Test that you can't go from FAULT to STANDBY while cooling,

        but after cooling is done then it may be OK.
        """
        remaining_cooldown = self.csc.lamp_model.get_remaining_cooldown()
        assert remaining_cooldown > 0

        with pytest.raises(salobj.AckError):
            await self.remote.cmd_standby.start()

        await self.wait_cooldown()

        if can_recover:
            await self.remote.cmd_standby.start()
            await self.assert_next_summary_state(state=salobj.State.STANDBY)
        else:
            with pytest.raises(salobj.AckError):
                await self.remote.cmd_standby.start()

    async def test_bin_script(self):
        await self.check_bin_script(
            name="ATWhiteLight",
            index=None,
            exe_name="run_atwhitelight",
        )

    async def test_chiller_alarms(self):
        """Test reporting of chiller alarms and warnings."""
        # Don't bother enabling the CSC; the focus is on connecting
        # and reporting the correct errors.
        async with self.make_csc(
            initial_state=salobj.State.DISABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.assert_next_summary_state(state=salobj.State.DISABLED)
            await self.assert_next_sample(
                topic=self.remote.evt_chillerConnected, connected=False
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampConnected, connected=False
            )
            await self.assert_next_sample(
                topic=self.remote.evt_chillerConnected, connected=True
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampConnected, connected=True
            )
            await self.assert_next_sample(
                topic=self.remote.evt_chillerWatchdog,
                controllerState=ChillerControllerState.STANDBY,
                pumpRunning=False,
                alarmsPresent=0,
                warningsPresent=0,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_chillerAlarms,
                level1=0,
                level21=0,
                level22=0,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_chillerWarnings,
                warnings=0,
            )

            mock_chiller = self.csc.chiller_model.mock_chiller
            is_first = True
            for l1_alarms, l21_alarms, l22_alarms, warnings in (
                (1, 2, 4, 8),
                (3, 5, 7, 9),
            ):
                mock_chiller.l1_alarms = l1_alarms
                mock_chiller.l21_alarms = l21_alarms
                mock_chiller.l22_alarms = l22_alarms
                mock_chiller.warnings = warnings
                if is_first:
                    await self.assert_next_sample(
                        topic=self.remote.evt_chillerWatchdog,
                        controllerState=ChillerControllerState.STANDBY,
                        pumpRunning=False,
                        alarmsPresent=True,
                        warningsPresent=True,
                    )
                is_first = False
                await self.assert_next_sample(
                    topic=self.remote.evt_chillerAlarms,
                    level1=l1_alarms,
                    level21=l21_alarms,
                    level22=l22_alarms,
                )
                await self.assert_next_sample(
                    topic=self.remote.evt_chillerWarnings,
                    warnings=warnings,
                )

    async def test_chiller_alarm_turns_lamp_off(self):
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.assert_next_summary_state(state=salobj.State.ENABLED)
            await self.assert_next_sample(
                topic=self.remote.evt_errorCode,
                errorCode=0,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.UNKNOWN,
                controllerState=LampControllerState.UNKNOWN,
                controllerError=LampControllerError.UNKNOWN,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.OFF,
                controllerState=LampControllerState.STANDBY,
                controllerError=LampControllerError.NONE,
            )

            await self.remote.cmd_startChiller.start()

            await self.remote.cmd_turnLampOn.start()
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.TURNING_ON,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.WARMUP,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
            )

            mock_chiller = self.csc.chiller_model.mock_chiller
            mock_chiller.l1_alarms = 1

            await self.assert_next_summary_state(state=salobj.State.FAULT)
            await self.assert_next_sample(
                topic=self.remote.evt_errorCode,
                errorCode=ErrorCode.CHILLER_ERROR,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.TURNING_OFF,
                controllerState=LampControllerState.COOLDOWN,
                controllerError=LampControllerError.NONE,
            )
            await self.check_fault_to_standby_while_cooling(can_recover=False)

    async def test_chiller_connect_timeout(self):
        """Test that we cannot configure the chiller in time."""
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            self.csc.chiller_make_connect_time_out = True
            await self.assert_next_summary_state(salobj.State.STANDBY)
            await self.remote.cmd_start.set_start()
            await self.assert_next_summary_state(salobj.State.FAULT)
            await self.remote.cmd_standby.set_start()
            await self.assert_next_summary_state(salobj.State.STANDBY)

    async def test_chiller_disconnect_turns_lamp_off(self):
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.assert_next_summary_state(state=salobj.State.ENABLED)
            await self.assert_next_sample(
                topic=self.remote.evt_errorCode,
                errorCode=0,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.UNKNOWN,
                controllerState=LampControllerState.UNKNOWN,
                controllerError=LampControllerError.UNKNOWN,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.OFF,
                controllerState=LampControllerState.STANDBY,
                controllerError=LampControllerError.NONE,
            )

            await self.remote.cmd_startChiller.start()

            await self.remote.cmd_turnLampOn.start()
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.TURNING_ON,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.WARMUP,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
            )

            # Kill the connection to the chiller.
            # This should send the CSC to fault and turn off the lamp.
            await self.csc.chiller_model.disconnect()

            await self.assert_next_summary_state(state=salobj.State.FAULT)
            await self.assert_next_sample(
                topic=self.remote.evt_errorCode,
                errorCode=ErrorCode.CHILLER_DISCONNECTED,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.TURNING_OFF,
            )
            await self.check_fault_to_standby_while_cooling(can_recover=True)

    async def test_chiller_off_turns_lamp_off(self):
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.assert_next_summary_state(state=salobj.State.ENABLED)
            await self.assert_next_sample(
                topic=self.remote.evt_errorCode,
                errorCode=0,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.UNKNOWN,
                controllerError=LampControllerError.UNKNOWN,
                controllerState=LampControllerState.UNKNOWN,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.OFF,
                controllerState=LampControllerState.STANDBY,
                controllerError=LampControllerError.NONE,
            )

            await self.remote.cmd_startChiller.start()

            await self.remote.cmd_turnLampOn.start()
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.TURNING_ON,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.WARMUP,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
            )

            await self.csc.chiller_model.stop_cooling()

            await self.assert_next_summary_state(state=salobj.State.FAULT)
            await self.assert_next_sample(
                topic=self.remote.evt_errorCode,
                errorCode=ErrorCode.NOT_CHILLING_WITH_LAMP_ON,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.TURNING_OFF,
                controllerState=LampControllerState.COOLDOWN,
                controllerError=LampControllerError.NONE,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.COOLDOWN,
                controllerState=LampControllerState.COOLDOWN,
                controllerError=LampControllerError.NONE,
            )
            await self.check_fault_to_standby_while_cooling(can_recover=True)

    async def test_chiller_pump_off_turns_lamp_off(self):
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.assert_next_summary_state(state=salobj.State.ENABLED)
            await self.assert_next_sample(
                topic=self.remote.evt_errorCode,
                errorCode=0,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.UNKNOWN,
                controllerState=LampControllerState.UNKNOWN,
                controllerError=LampControllerError.UNKNOWN,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.OFF,
                controllerState=LampControllerState.STANDBY,
                controllerError=LampControllerError.NONE,
            )

            await self.remote.cmd_startChiller.start()

            await self.remote.cmd_turnLampOn.start()
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.TURNING_ON,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.WARMUP,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
            )

            self.csc.chiller_model.mock_chiller.pump_running = False

            await self.assert_next_summary_state(state=salobj.State.FAULT)
            await self.assert_next_sample(
                topic=self.remote.evt_errorCode,
                errorCode=ErrorCode.NOT_CHILLING_WITH_LAMP_ON,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.TURNING_OFF,
                controllerState=LampControllerState.COOLDOWN,
                controllerError=LampControllerError.NONE,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.COOLDOWN,
                controllerState=LampControllerState.COOLDOWN,
                controllerError=LampControllerError.NONE,
            )
            await self.check_fault_to_standby_while_cooling(can_recover=True)

    async def test_chiller_telemetry(self):
        async with self.make_csc(
            initial_state=salobj.State.DISABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            mock_chiller = self.csc.chiller_model.mock_chiller
            data = await self.remote.tel_chillerFanSpeeds.next(
                flush=False, timeout=STD_TIMEOUT
            )
            for i in range(4):
                salname = f"fan{i+1}"
                # The chiller reports fan speeds rounded to the nearest int
                assert getattr(data, salname) == pytest.approx(
                    mock_chiller.fan_speeds[i], abs=0.5
                )
            data = await self.remote.tel_chillerTemperatures.next(
                flush=False, timeout=STD_TIMEOUT
            )
            assert data.setTemperature == pytest.approx(
                self.csc.config.chiller.initial_temperature
            )
            for salname, attrname in (
                ("ambientTemperature", "ambient_temperature"),
                ("returnTemperature", "return_temperature"),
                ("supplyTemperature", "supply_temperature"),
            ):
                with self.subTest(salname=salname, attrname=attrname):
                    if salname == "returnTemperature" and not READ_RETURN_TEMPERATURE:
                        assert math.isnan(data.returnTemperature)
                    else:
                        # The chiller reports temperatures rounded to 1/10
                        assert getattr(data, salname) == pytest.approx(
                            getattr(mock_chiller, attrname), abs=0.05
                        )
            data = await self.remote.tel_chillerCoolantFlow.next(
                flush=False, timeout=STD_TIMEOUT
            )
            # The chiller reports flow rounded to 1/10
            assert data.flow == pytest.approx(mock_chiller.coolant_flow_rate, abs=0.05)
            data = await self.remote.tel_chillerTECBankCurrents.next(
                flush=False, timeout=STD_TIMEOUT
            )
            for i in range(2):
                salname = f"bank{i+1}"
                assert getattr(data, salname) == pytest.approx(
                    mock_chiller.tec_bank_currents[i], abs=0.0005
                )
            data = await self.remote.tel_chillerTECDrive.next(
                flush=False, timeout=STD_TIMEOUT
            )
            assert data.isCooling == mock_chiller.is_cooling
            assert data.level == pytest.approx(mock_chiller.tec_drive_level, abs=0.5)

    async def test_decode_lamp_errors(self):
        # Use DISABLED state so the lamp is not forced off (which generates
        # extra lampState events that complicate the test).
        async with self.make_csc(
            initial_state=salobj.State.DISABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.assert_next_summary_state(state=salobj.State.DISABLED)
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.UNKNOWN,
                controllerState=LampControllerState.UNKNOWN,
                controllerError=LampControllerError.UNKNOWN,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.OFF,
                controllerState=LampControllerState.STANDBY,
                controllerError=LampControllerError.NONE,
            )

            self.csc.lamp_model.labjack.set_error(LampControllerError.ACCESS_DOOR)
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.OFF,
                controllerState=LampControllerState.ERROR,
                controllerError=LampControllerError.UNKNOWN,
            )
            await self.assert_next_summary_state(salobj.State.FAULT)

            # Required time to decode the blinking error signal
            # is the value of the error enum + 1 second
            decode_duration = int(LampControllerError.ACCESS_DOOR) + 1
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.OFF,
                controllerState=LampControllerState.ERROR,
                controllerError=LampControllerError.ACCESS_DOOR,
                timeout=STD_TIMEOUT + decode_duration,
            )

            self.csc.lamp_model.labjack.set_error(LampControllerError.NONE)
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.OFF,
                controllerState=LampControllerState.STANDBY,
                controllerError=LampControllerError.NONE,
            )

            # Now test an error code that is larger than any known
            too_large_error_code = max(LampControllerError) + 1
            self.csc.lamp_model.labjack.set_error(too_large_error_code)
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.OFF,
                controllerState=LampControllerState.ERROR,
                controllerError=LampControllerError.UNKNOWN,
            )
            await asyncio.sleep(too_large_error_code + 1)
            assert (
                self.csc.evt_lampState.data.controllerError
                == LampControllerError.UNKNOWN
            )

    async def test_lamp_connect_timeout(self):
        """Test that we cannot connect to the lamp in time."""
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            self.csc.lamp_make_connect_time_out = True
            await self.assert_next_summary_state(salobj.State.STANDBY)
            await self.remote.cmd_start.set_start()
            await self.assert_next_summary_state(salobj.State.FAULT)
            await self.remote.cmd_standby.set_start()
            await self.assert_next_summary_state(salobj.State.STANDBY)

    async def test_lamp_disconnect_fault(self):
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.assert_next_summary_state(state=salobj.State.ENABLED)
            await self.assert_next_sample(
                topic=self.remote.evt_errorCode,
                errorCode=0,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampConnected,
                connected=False,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampConnected,
                connected=True,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.UNKNOWN,
                controllerState=LampControllerState.UNKNOWN,
                controllerError=LampControllerError.UNKNOWN,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.OFF,
                controllerState=LampControllerState.STANDBY,
                controllerError=LampControllerError.NONE,
            )

            await self.remote.cmd_startChiller.start()

            await self.remote.cmd_turnLampOn.start()
            data = await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.TURNING_ON,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
                cooldownEndTime=0,
            )
            assert data.setPower == pytest.approx(self.csc.config.lamp.default_power)
            previous_set_power = data.setPower
            previous_warmup_end_time = data.warmupEndTime
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.WARMUP,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
                setPower=previous_set_power,
                cooldownEndTime=0,
                warmupEndTime=previous_warmup_end_time,
            )

            # Disconnect lamp.
            await self.csc.lamp_model.disconnect()
            await self.assert_next_sample(
                topic=self.remote.evt_lampConnected,
                connected=False,
            )
            # The CSC has no idea if the lamp is on or off,
            # so does not set lamp_off_time, so cooldownEndTime=0.
            data = await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.UNKNOWN,
                controllerState=LampControllerState.UNKNOWN,
                controllerError=LampControllerError.UNKNOWN,
                setPower=0,
                cooldownEndTime=0,
                warmupEndTime=previous_warmup_end_time,
            )

            # The CSC should react by going to fault.
            await self.assert_next_summary_state(salobj.State.FAULT)
            await self.assert_next_sample(
                topic=self.remote.evt_errorCode,
                errorCode=ErrorCode.LAMP_DISCONNECTED,
            )
            assert self.csc.chiller_connected
            assert not self.csc.lamp_connected

            # It should be possible to go to standby immediately
            # because we lost the knowledge needed to know if we need to wait.
            # Note: in a real system the lamp will still be on, but in
            # simulation mode the mock labjack interface is destroyed when
            # the lamp model disconnects, so don't try to test that.
            await self.remote.cmd_standby.start()
            await self.assert_next_summary_state(state=salobj.State.STANDBY)

    async def test_lamp_error_turns_lamp_off(self):
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.assert_next_summary_state(state=salobj.State.ENABLED)
            await self.assert_next_sample(
                topic=self.remote.evt_errorCode,
                errorCode=0,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.UNKNOWN,
                controllerState=LampControllerState.UNKNOWN,
                controllerError=LampControllerError.UNKNOWN,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.OFF,
                controllerState=LampControllerState.STANDBY,
                controllerError=LampControllerError.NONE,
            )

            await self.remote.cmd_startChiller.start()

            await self.remote.cmd_turnLampOn.start()
            data = await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.TURNING_ON,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
                cooldownEndTime=0,
            )
            assert data.setPower == pytest.approx(self.csc.config.lamp.default_power)
            previous_set_power = data.setPower
            previous_warmup_end_time = data.warmupEndTime
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.WARMUP,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
                setPower=previous_set_power,
                cooldownEndTime=0,
                warmupEndTime=previous_warmup_end_time,
            )

            start_tai = current_tai()
            # Put lamp controller into error state; any error will do
            self.csc.lamp_model.labjack.set_error(LampControllerError.LAMP_STUCK_ON)
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.WARMUP,
                controllerState=LampControllerState.ERROR,
                controllerError=LampControllerError.UNKNOWN,
            )

            # The CSC should react by going to fault and turning off the lamp
            # but leave the lamp and chiller connected.
            await self.assert_next_summary_state(salobj.State.FAULT)
            await self.assert_next_sample(
                topic=self.remote.evt_errorCode,
                errorCode=ErrorCode.LAMP_ERROR,
            )
            data = await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.TURNING_OFF,
                controllerState=LampControllerState.ERROR,
                controllerError=LampControllerError.UNKNOWN,
                setPower=0,
                warmupEndTime=previous_warmup_end_time,
            )
            assert (
                data.cooldownEndTime >= start_tai + self.csc.config.lamp.cooldown_period
            )
            assert self.csc.chiller_connected
            assert self.csc.lamp_connected
            await self.check_fault_to_standby_while_cooling(can_recover=False)

    async def test_lamp_fails_to_turn_off(self):
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.assert_next_summary_state(state=salobj.State.ENABLED)
            await self.assert_next_sample(
                topic=self.remote.evt_errorCode,
                errorCode=0,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.UNKNOWN,
                controllerState=LampControllerState.UNKNOWN,
                controllerError=LampControllerError.UNKNOWN,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.OFF,
                controllerState=LampControllerState.STANDBY,
                controllerError=LampControllerError.NONE,
            )
            self.csc.lamp_model.labjack.allow_photosensor_off = False

            await self.remote.cmd_startChiller.start()

            await self.remote.cmd_turnLampOn.start()
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.TURNING_ON,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.WARMUP,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
            )
            await self.remote.cmd_turnLampOff.set_start(force=True)
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.TURNING_OFF,
                controllerState=LampControllerState.COOLDOWN,
                controllerError=LampControllerError.NONE,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.UNEXPECTEDLY_ON,
                controllerState=LampControllerState.COOLDOWN,
                controllerError=LampControllerError.NONE,
            )
            await self.assert_next_summary_state(state=salobj.State.FAULT)
            # Note: the CSC does not try to turn the lamp off again
            # (it was already commanded off and doing it again should not
            # have any affect), so the next lamp state is published
            # when the lamp controller's own cooldown timer expires:
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.UNEXPECTEDLY_ON,
                controllerState=LampControllerState.STANDBY,
                controllerError=LampControllerError.NONE,
            )

            await self.remote.cmd_standby.start()
            await self.assert_next_summary_state(state=salobj.State.STANDBY)

    async def test_lamp_fails_to_turn_on(self):
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.assert_next_summary_state(state=salobj.State.ENABLED)
            await self.assert_next_sample(
                topic=self.remote.evt_errorCode,
                errorCode=0,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.UNKNOWN,
                controllerState=LampControllerState.UNKNOWN,
                controllerError=LampControllerError.UNKNOWN,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.OFF,
                controllerState=LampControllerState.STANDBY,
                controllerError=LampControllerError.NONE,
            )
            self.csc.lamp_model.labjack.allow_photosensor_on = False

            await self.remote.cmd_startChiller.start()

            await self.remote.cmd_turnLampOn.start()
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.TURNING_ON,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.UNEXPECTEDLY_OFF,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
            )
            await self.assert_next_summary_state(state=salobj.State.FAULT)
            # The CSC turns off turns off the lamp.
            # The photo sensor sees no light so the basicState
            # goes directly to COOLDOWN (with no TURNING_OFF phase).
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.OFF,
                controllerState=LampControllerState.COOLDOWN,
                controllerError=LampControllerError.NONE,
            )

    async def test_reconnect(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.assert_next_summary_state(state=salobj.State.STANDBY)
            await self.assert_next_sample(
                topic=self.remote.evt_chillerConnected, connected=False
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampConnected, connected=False
            )

            await self.remote.cmd_start.start()
            await self.assert_next_summary_state(state=salobj.State.DISABLED)
            await self.assert_next_sample(
                topic=self.remote.evt_chillerConnected, connected=True
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampConnected, connected=True
            )

            await self.remote.cmd_standby.start()
            await self.assert_next_summary_state(state=salobj.State.STANDBY)
            await self.assert_next_sample(
                topic=self.remote.evt_chillerConnected, connected=False
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampConnected, connected=False
            )

            await self.remote.cmd_start.start()
            await self.assert_next_summary_state(state=salobj.State.DISABLED)
            await self.assert_next_sample(
                topic=self.remote.evt_chillerConnected, connected=True
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampConnected, connected=True
            )

    async def test_set_chiller_temperature(self):
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            # Check the control sensor (which must be SUPPLY for our
            # current chiller).
            assert (
                self.csc.chiller_model.mock_chiller.control_sensor
                == atwhitelight.ChillerControlSensor.SUPPLY
            )

            data = await self.remote.tel_chillerTemperatures.next(
                flush=True, timeout=STD_TIMEOUT
            )
            assert data.setTemperature == pytest.approx(
                self.csc.config.chiller.initial_temperature, abs=0.05
            )

            # Values will be rounded to the nearest 1/10 C,
            # so specify target values that are already rounded
            # or relax the match tolerance.
            for target_temp in (18, 20):
                await self.remote.cmd_setChillerTemperature.set_start(
                    temperature=target_temp, timeout=STD_TIMEOUT
                )
                data = await self.remote.tel_chillerTemperatures.next(
                    flush=True, timeout=STD_TIMEOUT
                )
                assert data.setTemperature == pytest.approx(target_temp)

            # A value out of range of configured
            # low/high_supply_temperature_warning should be rejected.
            for bad_target_temp in (
                self.csc.config.chiller.low_supply_temperature_warning - 0.01,
                self.csc.config.chiller.high_supply_temperature_warning + 0.01,
            ):
                with pytest.raises(salobj.AckError):
                    await self.remote.cmd_setChillerTemperature.set_start(
                        temperature=bad_target_temp, timeout=STD_TIMEOUT
                    )
                assert self.csc.summary_state == salobj.State.ENABLED

    async def test_shutter_move(self):
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            # From the CSC starting
            await self.assert_next_sample(
                topic=self.remote.evt_shutterState,
                commandedState=ShutterState.UNKNOWN,
                actualState=ShutterState.UNKNOWN,
                enabled=False,
            )
            # The mock lamp controller starts with the shutter closed
            await self.assert_next_sample(
                topic=self.remote.evt_shutterState,
                actualState=ShutterState.CLOSED,
                enabled=False,
            )

            # Open the shutter
            await self.remote.cmd_openShutter.start()
            await self.assert_next_sample(
                topic=self.remote.evt_shutterState,
                commandedState=ShutterState.OPEN,
                enabled=True,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_shutterState,
                commandedState=ShutterState.OPEN,
                actualState=ShutterState.UNKNOWN,
                enabled=True,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_shutterState,
                commandedState=ShutterState.OPEN,
                actualState=ShutterState.OPEN,
                enabled=True,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_shutterState,
                commandedState=ShutterState.OPEN,
                actualState=ShutterState.OPEN,
                enabled=False,
            )

            # Close the shutter
            await self.remote.cmd_closeShutter.start()
            await self.assert_next_sample(
                topic=self.remote.evt_shutterState,
                commandedState=ShutterState.CLOSED,
                enabled=True,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_shutterState,
                commandedState=ShutterState.CLOSED,
                actualState=ShutterState.UNKNOWN,
                enabled=True,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_shutterState,
                commandedState=ShutterState.CLOSED,
                actualState=ShutterState.CLOSED,
                enabled=True,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_shutterState,
                commandedState=ShutterState.CLOSED,
                actualState=ShutterState.CLOSED,
                enabled=False,
            )

            # Timeout
            self.csc.lamp_model.labjack.shutter_duration = (
                self.csc.config.lamp.shutter_timeout * 2
            )
            open_task = asyncio.create_task(self.remote.cmd_openShutter.start())
            await self.assert_next_sample(
                topic=self.remote.evt_shutterState,
                commandedState=ShutterState.OPEN,
                enabled=True,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_shutterState,
                commandedState=ShutterState.OPEN,
                actualState=ShutterState.UNKNOWN,
                enabled=True,
            )
            with salobj.assertRaisesAckError(ack=salobj.SalRetCode.CMD_TIMEOUT):
                await open_task
            await self.assert_next_sample(
                topic=self.remote.evt_shutterState,
                commandedState=ShutterState.OPEN,
                actualState=ShutterState.UNKNOWN,
                enabled=False,
            )

            # Test cannot move due to invalid state
            self.csc.lamp_model.labjack.shutter_closed_switch = True
            self.csc.lamp_model.labjack.shutter_open_switch = True
            await self.assert_next_sample(
                topic=self.remote.evt_shutterState,
                commandedState=ShutterState.OPEN,
                actualState=ShutterState.INVALID,
                enabled=False,
            )
            with salobj.assertRaisesAckError(ack=salobj.SalRetCode.CMD_FAILED):
                await self.remote.cmd_openShutter.start()
            with salobj.assertRaisesAckError(ack=salobj.SalRetCode.CMD_FAILED):
                await self.remote.cmd_closeShutter.start()

    async def test_standard_state_transitions(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.check_standard_state_transitions(
                enabled_commands=[
                    "closeShutter",
                    "openShutter",
                    "turnLampOn",
                    "turnLampOff",
                    "setChillerTemperature",
                    "startChiller",
                    "stopChiller",
                ]
            )

    async def test_turn_lamp_on(self):
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.assert_next_sample(
                topic=self.remote.evt_chillerConnected, connected=False
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampConnected, connected=False
            )
            await self.assert_next_sample(
                topic=self.remote.evt_chillerConnected, connected=True
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampConnected, connected=True
            )
            await self.assert_next_sample(
                topic=self.remote.evt_chillerWatchdog,
                controllerState=ChillerControllerState.STANDBY,
                pumpRunning=False,
                alarmsPresent=0,
                warningsPresent=0,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.UNKNOWN,
                controllerState=LampControllerState.UNKNOWN,
                controllerError=LampControllerError.UNKNOWN,
                setPower=0,
                cooldownEndTime=0,
                warmupEndTime=0,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.OFF,
                controllerState=LampControllerState.STANDBY,
                controllerError=LampControllerError.NONE,
                setPower=0,
                cooldownEndTime=0,
                warmupEndTime=0,
            )

            # Cannot turn on lamp while not cooling
            with pytest.raises(salobj.AckError):
                await self.remote.cmd_turnLampOn.start()

            await self.remote.cmd_startChiller.start()
            await self.assert_next_sample(
                topic=self.remote.evt_chillerWatchdog,
                controllerState=ChillerControllerState.RUN,
                pumpRunning=True,
                alarmsPresent=0,
                warningsPresent=0,
            )

            start_tai = current_tai()
            on_power = 922  # Arbitrary valid value
            await self.remote.cmd_turnLampOn.set_start(power=on_power)
            data = await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.TURNING_ON,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
                cooldownEndTime=0,
            )
            assert data.setPower == pytest.approx(on_power)
            assert data.warmupEndTime >= start_tai + self.csc.config.lamp.warmup_period
            previous_power = data.setPower
            previous_warmupEndTime = data.warmupEndTime
            data = await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.WARMUP,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
                setPower=previous_power,
                cooldownEndTime=0,
                warmupEndTime=previous_warmupEndTime,
            )

            # Can start cooling while cooling
            await self.remote.cmd_startChiller.start()

            # Cannot stop cooling off while lamp is on
            with pytest.raises(salobj.AckError):
                await self.remote.cmd_stopChiller.start()

            # Set default power
            await self.remote.cmd_turnLampOn.set_start(power=0)
            data = await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.WARMUP,
                controllerState=LampControllerState.ON,
                controllerError=LampControllerError.NONE,
                cooldownEndTime=0,
                warmupEndTime=previous_warmupEndTime,
            )
            assert data.setPower == pytest.approx(self.csc.config.lamp.default_power)

            for bad_power in (779.9, 1200.1):
                with pytest.raises(salobj.AckError):
                    await self.remote.cmd_turnLampOn.set_start(power=bad_power)

            # Cannot turn lamp off this soon without force=True
            with pytest.raises(salobj.AckError):
                await self.remote.cmd_turnLampOff.start()

            start_tai = current_tai()
            await self.remote.cmd_turnLampOff.set_start(force=True)
            data = await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.TURNING_OFF,
                controllerState=LampControllerState.COOLDOWN,
                controllerError=LampControllerError.NONE,
                setPower=0,
                warmupEndTime=previous_warmupEndTime,
            )
            assert (
                data.cooldownEndTime >= start_tai + self.csc.config.lamp.cooldown_period
            )
            previous_cooldownEndTime = data.cooldownEndTime
            data = await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.COOLDOWN,
                controllerState=LampControllerState.COOLDOWN,
                controllerError=LampControllerError.NONE,
                setPower=0,
                cooldownEndTime=previous_cooldownEndTime,
                warmupEndTime=previous_warmupEndTime,
            )
            data = await self.remote.evt_lampOnHours.next(
                flush=False, timeout=STD_TIMEOUT
            )
            estimated_sec = (
                self.csc.lamp_model.lamp_off_time - self.csc.lamp_model.lamp_on_time
            )
            assert estimated_sec > 0
            assert data.hours == pytest.approx(estimated_sec / 3600)

            # Cannot turn the chiller off during cooldown
            with pytest.raises(salobj.AckError):
                await self.remote.cmd_stopChiller.start()

            # Cannot turn the lamp on during cooldown
            with pytest.raises(salobj.AckError):
                await self.remote.cmd_turnLampOn.start()

            # The lamp controller's internal cooldown timer should be shorter
            # than the CSC's cooldown timer
            data = await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.COOLDOWN,
                controllerState=LampControllerState.STANDBY,
                controllerError=LampControllerError.NONE,
                setPower=0,
            )
            data = await self.assert_next_sample(
                topic=self.remote.evt_lampState,
                basicState=LampBasicState.OFF,
                controllerState=LampControllerState.STANDBY,
                controllerError=LampControllerError.NONE,
                setPower=0,
            )

            await self.remote.cmd_stopChiller.start()
            await self.assert_next_sample(
                topic=self.remote.evt_chillerWatchdog,
                controllerState=ChillerControllerState.STANDBY,
                pumpRunning=False,
                alarmsPresent=0,
                warningsPresent=0,
            )

    async def wait_cooldown(self):
        """Wait for the lamp to cool down."""
        remaining_cooldown = self.csc.lamp_model.get_remaining_cooldown()
        assert remaining_cooldown > 0

        # The maximum number of basic states we expect to see.
        max_basic_states = 3

        # Wait for CSC cooldown to end.
        # Normally the lamp controller's cooldown timer expires first,
        # then the CSC's timer. But the lamp controller's cooldown timer
        # is irrelevant if the lamp controller is in an error state.
        for _ in range(max_basic_states):
            data = await self.remote.evt_lampState.next(
                flush=False, timeout=STD_TIMEOUT + remaining_cooldown
            )
            match data.basicState:
                case LampBasicState.OFF:
                    return
                case LampBasicState.TURNING_OFF | LampBasicState.COOLDOWN:
                    continue
                case _:
                    self.fail(
                        f"lampState.basicState={data.basicState} != "
                        f"{LampBasicState.OFF!r} or {LampBasicState.COOLDOWN!r}"
                    )
        self.fail("Bug: OFF state not seen. Increase max_basic_states?")
