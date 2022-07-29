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

__all__ = ["ChillerModel"]

import asyncio
import functools
import inspect
import math

from lsst.ts import salobj
from lsst.ts import utils
from lsst.ts.idl.enums.ATWhiteLight import ChillerControllerState
from .chiller_client import ChillerClient
from .mock_chiller import MockChiller
from .chiller_base import (
    ChillerControlSensor,
    ChillerThresholdType,
    format_chiller_command_value,
)


def parse_bool_str(bool_str):
    try:
        return {"0": False, "1": True}[bool_str]
    except KeyError:
        raise ValueError(f"bool_str={bool_str!r} must be '0' or '1'")


class ConnectedError(Exception):
    pass


ERROR_CODES = {
    "0": "",
    "1": "checksum error",
    "2": "invalid command name",
    "3": "parameter out of range",
    "4": "invalid message length",
    "5": "sensor or feature not configured or used",
}

# Read the return temperature?
# Our ThermoTek T257P is giving unrealistic readings, so don't bother.
READ_RETURN_TEMPERATURE = False

NUM_READ_TEMPERATURES = 4 if READ_RETURN_TEMPERATURE else 3

FAN_NUMBERS = (1, 2, 3, 4)


class ChillerModel:
    """Interface to the ThermoTek chiller.

    Connect, disconnect, send commands, and monitor state.

    Parameters
    ----------
    config : `types.SimpleNamespace`
        Chiller-specific configuration.
    topics : `lsst.ts.salobj.BaseCsc` or `types.SimpleNamespace`
        The CSC or a struct with chiller-specific write topics.
    log : `logging.Logger`
        Logger.
    status_callback : `awaitable` or `None`, optional
        Coroutine to call when evt_chillerWatchdog or evt_chillerConnected
        changes. It receives one argument: this model.
    simulate : `bool`, optional
        Run in simulation mode?
        If true then run a mock chiller.

    Raises
    ------
    TypeError
        If ``status_callback`` is not None and not a coroutine.

    Notes
    -----
    The ThermoTek T257P can only servo to the supply temperature,
    despite the command manual offering a command to set it to other sensors.
    In addition, the value read by the return sensor is not believable.
    """

    def __init__(self, config, topics, log, status_callback, simulate):
        if status_callback is not None and not inspect.iscoroutinefunction(
            status_callback
        ):
            raise TypeError(
                f"status_callback={status_callback} must be None or a coroutine"
            )

        self.config = config
        self.topics = topics
        self.log = log.getChild("ChillerModel")
        self.status_callback = status_callback
        self.simulate = simulate

        self.device_id = "01"
        self.topics.tel_chillerTemperatures.set(
            setTemperature=self.config.initial_temperature,
            supplyTemperature=math.nan,
            returnTemperature=math.nan,
            ambientTemperature=math.nan,
        )

        self.reply_handlers = {
            "01": self.handle_watchdog,
            "03": functools.partial(
                self.handle_read_temperature, field_name="setTemperature"
            ),
            "04": functools.partial(
                self.handle_read_temperature, field_name="supplyTemperature"
            ),
            "07": functools.partial(
                self.handle_read_temperature, field_name="returnTemperature"
            ),
            "08": functools.partial(
                self.handle_read_temperature, field_name="ambientTemperature"
            ),
            "09": self.handle_read_coolant_flow_rate,
            "10": functools.partial(
                self.handle_read_tec_bank_currents, field_name="bank1"
            ),
            "11": functools.partial(
                self.handle_read_tec_bank_currents, field_name="bank2"
            ),
            "13": self.handle_read_tec_drive_level,
            "15": self.handle_set_chiller_status,
            "16": self.handle_set_control_sensor,
            "17": self.handle_set_control_temperature,
            "18": self.handle_read_l1_alarms,
            "19": self.handle_read_l2_alarms,
            "20": self.handle_read_warnings,
            "21": self.handle_set_warning_threshold,
            "22": self.handle_set_warning_threshold,
            "23": self.handle_set_warning_threshold,
            "24": self.handle_set_warning_threshold,
            "25": self.handle_set_warning_threshold,
            "26": self.handle_set_alarm_threshold,
            "27": self.handle_set_alarm_threshold,
            "28": self.handle_set_alarm_threshold,
            "29": self.handle_set_alarm_threshold,
            "30": self.handle_set_alarm_threshold,
            "50": functools.partial(self.handle_read_fan_speed, fan_num=1),
            "51": functools.partial(self.handle_read_fan_speed, fan_num=2),
            "52": functools.partial(self.handle_read_fan_speed, fan_num=3),
            "53": functools.partial(self.handle_read_fan_speed, fan_num=4),
        }

        self.client = None
        self.mock_chiller = None
        self.watchdog_task = utils.make_done_future()
        self.telemetry_task = utils.make_done_future()

        # Set when connected and watchdog data has been seen.
        # Cleared when disconnected.
        self.configured_event = asyncio.Event()

        # chiller state
        self.chiller_com_lock = asyncio.Lock()
        self.controller_state = None
        self.chillerStatus = None
        self.setTemp = None
        self.chillerUptime = None

    async def close(self):
        await self.disconnect()
        if self.mock_chiller is not None:
            await self.mock_chiller.close()
            self.mock_chiller = None

    @property
    def connected(self):
        """Return True if connected to the server and the configuration
        commands have run.
        """
        return self.client is not None and self.client.connected

    @property
    def configured(self):
        """Return True if connected to the server and the configuration
        commands have run.
        """
        return self.connected and self.configured_event.is_set()

    async def connect(self):
        """Connect to the chiller and configure it.

        Start background tasks that keep the model up-to-date.
        """
        await self.disconnect()
        if self.simulate:
            if self.mock_chiller is None:
                self.mock_chiller = MockChiller(log=self.log)
                await self.mock_chiller.start_task
            host = self.mock_chiller.host
            port = self.mock_chiller.port
        else:
            host = self.config.host
            port = self.config.port

        self.log.debug("Create ChillerClient with host=%s, port=%s", host, port)
        self.client = ChillerClient(
            device_id=self.device_id,
            host=host,
            port=port,
            log=self.log,
            connect_timeout=self.config.connect_timeout,
            command_timeout=self.config.command_timeout,
        )
        await self.client.connect()
        await self.topics.evt_chillerConnected.set_write(connected=True)
        self.log.debug("Connected; configure chiller")
        await self.configure_chiller()
        await self.do_watchdog()
        self.watchdog_task = asyncio.create_task(self.watchdog_loop())
        self.telemetry_task = asyncio.create_task(self.telemetry_loop())
        self.configured_event.set()
        self.log.debug("Connected and configured")

    async def disconnect(self):
        """Disconnect from the chiller and cancel tasks."""
        self.configured_event.clear()
        result = await self.topics.evt_chillerConnected.set_write(connected=False)
        self.watchdog_task.cancel()
        self.telemetry_task.cancel()
        self.reset_seen()
        if self.client is not None:
            await self.client.disconnect()
        if result.did_change:
            await self.call_status_callback()

    async def call_status_callback(self):
        """Call the status callback, if there is one."""
        if self.status_callback is None:
            return
        try:
            await self.status_callback(self)
        except Exception:
            self.log.exception("status callback failed")

    def check_set_temperature(self, temperature):
        """Check a demand temperature to see if it is range.

        Parameters
        ----------
        temperature : `float`
            The temperature to check (C)

        Raises
        ------
        lsst.ts.salobj.ExpectedError
            If temperature < config.low_supply_temperature_warning
            or temperature > config.high_supply_temperature_warning
        """
        if temperature < self.config.low_supply_temperature_warning:
            raise salobj.ExpectedError(
                f"temperature={temperature} "
                f"< low_supply_temperature_warning={self.config.low_supply_temperature_warning}"
            )
        if temperature > self.config.high_supply_temperature_warning:
            raise salobj.ExpectedError(
                f"temperature={temperature} "
                f"> high_supply_temperature_warning={self.config.high_supply_temperature_warning}"
            )

    async def do_read_ambient_temperature(self):
        """Request ambient temperature, in C"""
        await self.run_command("08rAmbTemp")

    async def do_read_fan_speed(self, fan_num):
        """Read the speed of one fan, in revolutions per second.

        Parameters
        ----------
        fan_num : int in range [1, 4]
        """
        if fan_num not in FAN_NUMBERS:
            raise ValueError(f"fan_num={fan_num} must be in {FAN_NUMBERS}")
        cmd_num = fan_num + 49
        await self.run_command(str(cmd_num) + "rFanSpd" + str(fan_num))

    async def do_read_l1_alarms(self):
        """Read the level 1 alarm state"""
        await self.run_command("18rAlrmLv1")

    async def do_read_l2_alarms(self, sublevel):
        """Read the level 2 alarm state

        Parameters
        ----------
        sublevel : int
            which set of L2 alarms to query
            should be 1 or 2
        """
        if sublevel not in {1, 2}:
            raise ValueError(f"sublevel={sublevel} must be 1 or 2")
        await self.run_command(f"19rAlrmLv2{sublevel}")

    async def do_read_coolant_flow_rate(self):
        """Request coolant flow rate, in liters/minute"""
        await self.run_command("09rProsFlo")

    async def do_read_return_temperature(self):
        """Request await self.run_command(temperature, in C"""
        await self.run_command("07rReturnT")

    async def do_read_set_temperature(self):
        """Request set temperature, in C"""
        await self.run_command("03rSetTemp")

    async def do_read_supply_temperature(self):
        """Request supply temperature, in C"""
        await self.run_command("04rSupplyT")

    async def do_read_tec_bank1(self):
        """Request TEC Bank1 current, in DC Amps"""
        await self.run_command("10rTECB1Cr")

    async def do_read_tec_bank2(self):
        """Request TEC Bank2 current, in DC Amps"""
        await self.run_command("11rTECDrLv")

    async def do_read_tec_drive_level(self):
        """Request the TEC drive level and mode.

        The returned value is a percentage and a C or H for cool/heat mode.
        """
        await self.run_command("13rTECB2Cr")

    async def do_read_uptime(self):
        """Read the uptime."""
        msg = "49rUpTime_"
        await self.run_command(msg)

    async def do_read_warnings(self):
        """Read the warning state"""
        await self.run_command("20rWarnLv1")

    async def do_set_alarm_threshold(self, threshold_type, value):
        """Set an alarm threshold for coolant flow rate or one of several
        temperatures.

        Parameters
        ----------
        threshold_type : ChillerThresholdType
            Threshold type.
        value : float in range -999.9 to 999.9
            Threshold value:

            * Temperature is in C and may be negative or positive.
            * Flow is in liters/minute and must be positive.
        """
        if threshold_type == ChillerThresholdType.LowCoolantFlowRate and value <= 0:
            raise ValueError(
                f"value={value} must be positive for threshold_type={threshold_type!r}"
            )

        cmd_str = {
            ChillerThresholdType.HighSupplyTemperature: "26sHiSpTAl",
            ChillerThresholdType.LowSupplyTemperature: "27sLoSpTAl",
            ChillerThresholdType.HighAmbientTemperature: "28sHiAmTAl",
            ChillerThresholdType.LowAmbientTemperature: "29sLoAmTAl",
            ChillerThresholdType.LowCoolantFlowRate: "30sLoPFlAl",
        }.get(threshold_type)
        if cmd_str is None:
            raise ValueError(f"Unsupported threshold_type={threshold_type!r}")

        formatted_value = format_chiller_command_value(
            value, scale=10, nchar=5, signed=True
        )

        await self.run_command(cmd_str + formatted_value)

    async def do_set_chiller_status(self, status):
        """Set the chiller status.

        Parameters
        ----------
        status : int
            desired state: 0 = standby, 1 = run
        """
        if status not in (0, 1):
            raise ValueError(f"Invalid status={status}; must be 0 or 1")
        await self.run_command(f"15sStatus_{status}")

    async def do_set_control_sensor(self, sensor):
        """Set the sensor to match for temperature control.

        Parameters
        ----------
        sensor : `ChillerControlSensor`
            Sensor to match for temperature control.
        """
        sensor = ChillerControlSensor(sensor)
        await self.run_command(f"16sCtrlSen{sensor.value}")

    async def do_set_control_temperature(self, temperature):
        """Set the desired temperature.

        Parameters
        ----------
        temperature : float
            Temperature (C)
        """
        self.check_set_temperature(temperature)
        data = format_chiller_command_value(temperature, scale=10, nchar=5, signed=True)
        await self.run_command("17sCtrlTmp" + data)

    async def do_set_warning_threshold(self, threshold_type, value):
        """Set a warning threshold for coolant flow rate, or one of several
        temperatures.

        Parameters
        ----------
        threshold_type : ChillerThresholdType
            Threshold type.
        value : float in range -999.9 to 999.9
            Threshold value:

            * Temperature is in C and may be negative or positive.
            * Flow is in liters/minute and must be positive.
        """
        if threshold_type == ChillerThresholdType.LowCoolantFlowRate and value <= 0:
            raise ValueError(
                f"value={value} must be positive for threshold_type={threshold_type!r}"
            )

        cmd_str = {
            ChillerThresholdType.HighSupplyTemperature: "21sHiSpTWn",
            ChillerThresholdType.LowSupplyTemperature: "22sLoSpTWn",
            ChillerThresholdType.HighAmbientTemperature: "28sHiAmTWn",
            ChillerThresholdType.LowAmbientTemperature: "29sLoAmTWn",
            ChillerThresholdType.LowCoolantFlowRate: "30sLoPFlWn",
        }.get(threshold_type)
        if cmd_str is None:
            raise ValueError(f"Unsupported threshold_type={threshold_type!r}")

        formatted_value = format_chiller_command_value(
            value, scale=10, nchar=5, signed=True
        )

        await self.run_command(cmd_str + formatted_value)

    async def do_watchdog(self):
        """Request a watchdog packet"""
        await self.run_command("01WatchDog")

    def get_watchdog(self):
        """Get the current evt_chillerWatchdog data.

        Raise RuntimeError if not connected or if watchdog data
        has not been seen since the connection was made
        (which would be a bug, since the model should not report
        being connected until watchdog data is seen).
        """
        if not self.connected:
            raise RuntimeError("Not connected")
        if (
            not self.configured_event.is_set()
            or not self.topics.evt_chillerWatchdog.has_data
        ):
            raise RuntimeError("Bug: connected but watchdog data not available")
        return self.topics.evt_chillerWatchdog.data

    async def handle_reply(self, reply):
        """Handle a reply.

        Parse it and send it to the appropriate handle_x method.

        Parameters
        ----------
        reply : `str`
            Reply from the chiller, without the final checksum and \r.
        """
        self.log.debug("Handle chiller reply %s", reply)
        if reply[0] != "#":
            self.log.warning(f"Ignoring reply={reply!r}: first char not #")
            return

        if len(reply) < 14:
            self.log.warning(f"Ignoring invalid reply={reply!r}: too short")
            return

        # process the string
        # device_id = reply[1:3]
        cmd_id = reply[3:5]
        # error_code = reply[5]
        # command_name = reply[6:14]
        data = reply[14:]
        reply_handler = self.reply_handlers.get(cmd_id)
        if reply_handler is None:
            self.log.warning(f"Ignoring reply={reply!r}: unsupported cmd_id={cmd_id}")
            return
        try:
            await reply_handler(data)
        except Exception as e:
            self.log.warning(f"reply_handler {reply_handler} failed: {e!r}; continuing")

    def parse_flow(self, data):
        """Parse flow rate as a float in ?"""
        return int(data) / 10

    def parse_temperature(self, data):
        """Parse temperature as a float in deg C."""
        return int(data) / 10

    def parse_current(self, data):
        """Parses current as a float in Amps."""
        return int(data) / 1000

    async def handle_read_fan_speed(self, data, fan_num):
        if fan_num not in FAN_NUMBERS:
            self.log.warning(
                "Cannot parse fan speed reply: "
                f"fan_num={fan_num} must be one of {FAN_NUMBERS}"
            )
        field_name = f"fan{fan_num}"
        speed = float(data)
        self.topics.tel_chillerFanSpeeds.set(**{field_name: speed})
        self.seen_fan_speeds.add(field_name)
        if len(self.seen_fan_speeds) == len(FAN_NUMBERS):
            await self.topics.tel_chillerFanSpeeds.write()
            self.seen_fan_speeds = set()

    async def handle_read_l1_alarms(self, data):
        # Reverse the alarm string before parsing it as a hex integer.
        # See note in lsst.ts.idl.enums.ATWhiteLight.ChillerL1Alarms
        # for the reason.
        mask = int(data[::-1], 16)
        self.seen_alarms.add("level1")
        self.topics.evt_chillerAlarms.set(level1=mask)
        if len(self.seen_alarms) == 3:
            await self.topics.evt_chillerAlarms.write()
            self.seen_alarms = set()

    async def handle_read_l2_alarms(self, data):
        sublevel = data[0]
        # Reverse the alarm string before parsing it as a hex integer.
        # See note in lsst.ts.idl.enums.ATWhiteLight.ChillerL1Alarms
        # for the reason.
        mask = int(data[1:][::-1], 16)
        if sublevel == "1":
            self.seen_alarms.add("level21")
            self.topics.evt_chillerAlarms.set(level21=mask)
        elif sublevel == "2":
            self.seen_alarms.add("level22")
            self.topics.evt_chillerAlarms.set(level22=mask)
        else:
            self.log.warning(f"Cannot parse level 2 alarm data={data!r}")
        if len(self.seen_alarms) == 3:
            await self.topics.evt_chillerAlarms.write()
            self.seen_alarms = set()

    async def handle_read_coolant_flow_rate(self, data):
        # flow uses the same formatting as temp
        flow = self.parse_flow(data)
        await self.topics.tel_chillerCoolantFlow.set_write(flow=flow)

    async def handle_read_tec_bank_currents(self, data, field_name):
        current = self.parse_current(data)
        self.topics.tel_chillerTECBankCurrents.set(**{field_name: current})
        self.seen_tec_bank_currents.add(field_name)
        if len(self.seen_tec_bank_currents) >= 2:
            await self.topics.tel_chillerTECBankCurrents.write()
            self.seen_tec_bank_currents = set()

    async def handle_read_tec_drive_level(self, data):
        try:
            is_cooling = {"C": True, "H": False}[data[4]]
        except LookupError:
            self.log.warning(f"Unrecognized cooling mode {data[4]}; should be C or H")
            return
        level = float(data[:3])
        await self.topics.tel_chillerTECDrive.set_write(
            isCooling=is_cooling, level=level
        )

    async def handle_read_temperature(self, data, field_name):
        value = self.parse_temperature(data)
        self.topics.tel_chillerTemperatures.set(**{field_name: value})
        self.seen_temperatures.add(field_name)
        if len(self.seen_temperatures) == NUM_READ_TEMPERATURES:
            await self.topics.tel_chillerTemperatures.write()
            self.seen_temperatures = set()

    async def handle_read_warnings(self, data):
        # Reverse the alarm string before parsing it as a hex integer.
        # See note in lsst.ts.idl.enums.ATWhiteLight.ChillerL1Alarms
        # for the reason.
        mask = int(data[::-1], 16)
        await self.topics.evt_chillerWarnings.set_write(warnings=mask)

    async def handle_set_alarm_threshold(self, data):
        pass

    async def handle_set_chiller_status(self, data):
        pass

    async def handle_set_control_sensor(self, data):
        pass

    async def handle_set_control_temperature(self, data):
        self.setTemp = self.parse_temperature(data)

    async def handle_set_warning_threshold(self, data):
        pass

    async def handle_watchdog(self, data):
        try:
            controller_state = ChillerControllerState(int(data[0]))
            pump_running = parse_bool_str(data[1])
            alarms_present = parse_bool_str(data[2])
            warnings_present = parse_bool_str(data[3])
        except Exception:
            self.log.exception(
                f"Could not parse watchdog data: {data!r}; assuming the worst"
            )
            controller_state = ChillerControllerState.UNKNOWN
            pump_running = False
            alarms_present = True
            warnings_present = True

        result = await self.topics.evt_chillerWatchdog.set_write(
            controllerState=controller_state,
            pumpRunning=pump_running,
            alarmsPresent=alarms_present,
            warningsPresent=warnings_present,
        )

        if alarms_present:
            # Get detailed alarm information
            self.seen_alarms = set()
            await self.do_read_l1_alarms()
            await self.do_read_l2_alarms(sublevel=1),
            await self.do_read_l2_alarms(sublevel=2),
        else:
            await self.topics.evt_chillerAlarms.set_write(
                level1=0, level21=0, level22=0
            )

        if warnings_present:
            # Get detailed warning information
            await self.do_read_warnings()
        else:
            await self.topics.evt_chillerWarnings.set_write(warnings=0)

        if result.did_change:
            await self.call_status_callback()

    async def configure_chiller(self):
        """Run commands to set control sensor and alarm and warning levels."""

        # I would like to set the control sensor to
        # ChillerControlSensor.RETURN but the T247P doesn't support that.
        await self.do_set_control_temperature(
            temperature=self.topics.tel_chillerTemperatures.data.setTemperature
        )
        await self.do_set_alarm_threshold(
            threshold_type=ChillerThresholdType.HighSupplyTemperature,
            value=self.config.high_supply_temperature_alarm,
        ),
        await self.do_set_alarm_threshold(
            threshold_type=ChillerThresholdType.LowSupplyTemperature,
            value=self.config.low_supply_temperature_alarm,
        ),
        await self.do_set_alarm_threshold(
            threshold_type=ChillerThresholdType.HighAmbientTemperature,
            value=self.config.high_ambient_temperature_alarm,
        ),
        await self.do_set_alarm_threshold(
            threshold_type=ChillerThresholdType.LowAmbientTemperature,
            value=self.config.low_ambient_temperature_alarm,
        ),
        await self.do_set_alarm_threshold(
            threshold_type=ChillerThresholdType.LowCoolantFlowRate,
            value=self.config.low_coolant_flow_rate_alarm,
        ),
        await self.do_set_warning_threshold(
            threshold_type=ChillerThresholdType.HighSupplyTemperature,
            value=self.config.high_supply_temperature_warning,
        ),
        await self.do_set_warning_threshold(
            threshold_type=ChillerThresholdType.LowSupplyTemperature,
            value=self.config.low_supply_temperature_warning,
        ),
        await self.do_set_warning_threshold(
            threshold_type=ChillerThresholdType.HighAmbientTemperature,
            value=self.config.high_ambient_temperature_warning,
        ),
        await self.do_set_warning_threshold(
            threshold_type=ChillerThresholdType.LowAmbientTemperature,
            value=self.config.low_ambient_temperature_warning,
        ),
        await self.do_set_warning_threshold(
            threshold_type=ChillerThresholdType.LowCoolantFlowRate,
            value=self.config.low_coolant_flow_rate_warning,
        )

    def reset_seen(self):
        """Reset the seen_x attributes.

        The seen_x attributes are used topics which have multiple fields
        whose values are filled by separate commands.
        Each value is a set of topic field names.
        As each field is seen, add its name to the appropriate set,
        and if all fields have been seen, write the topic
        and reset the seen_x to an empty set.

        Call this method:

        * When you construct the model (to create the attributes)
        * When you disconnect
        * When you connect (to be paranoid)
        """
        self.seen_alarms = set()
        self.seen_fan_speeds = set()
        self.seen_tec_bank_currents = set()
        self.seen_temperatures = set()

    async def run_command(self, cmd):
        """Run a chiller command and handle the reply.

        If the command or reply handler fails, log an error
        and raise an exception.

        Parameters
        ----------
        cmd : `str`
            Command, with no device ID or checksum.

        Returns
        -------
        reply : `str`
            The reply, without the trailing checksum and "\r".
            You should not need this, since this method
            handles the reply before returning it.

        Raises
        ------
        ConnectedError
            If the chiller is not connected.

        RuntimeError
            If the chiller rejects the command,
            or a reply is not seen in time.

        Exception
            If the reply handler raises an exception.
        """
        if not self.connected:
            raise ConnectedError("Not connected")

        reply = await self.client.run_command(cmd)

        if len(reply) < 14:
            err_msg = f"Command {cmd} failed: reply={reply!r}"
            self.log.error(err_msg)
            raise RuntimeError(err_msg)

        error_code = reply[5]
        if error_code != "0":
            error_descr = ERROR_CODES.get(error_code, "Unrecognized error code")
            error_msg = f"Command {cmd} failed: {error_code}: {error_descr}"
            self.log.error(error_msg)
            raise RuntimeError(error_msg)

        try:
            await self.handle_reply(reply)
        except Exception:
            self.log.exception("Command handler failed")
            raise

    async def start_cooling(self):
        """Start cooling and wait for the watchdog to report it."""
        await self.do_set_chiller_status(1)
        await self.do_watchdog()

    async def stop_cooling(self):
        """Stop cooling and wait for the watchdog to report it."""
        await self.do_set_chiller_status(0)
        await self.do_watchdog()

    async def telemetry_loop(self):
        """Run telemetry commands at regular intervals."""
        try:
            while self.connected:
                await self.do_read_set_temperature()
                await self.do_read_supply_temperature()
                if READ_RETURN_TEMPERATURE:
                    await self.do_read_return_temperature()
                await self.do_read_ambient_temperature()

                await self.do_read_coolant_flow_rate()

                for fan_num in FAN_NUMBERS:
                    await self.do_read_fan_speed(fan_num)

                await self.do_read_tec_drive_level()
                await self.do_read_tec_bank1()
                await self.do_read_tec_bank2()

                await asyncio.sleep(self.config.telemetry_interval)
        except (asyncio.CancelledError, ConnectedError):
            self.log.debug("telemetry_loop ends")
        except Exception:
            self.log.exception("telemetry_loop failed")
            # Don't await disconnect because it cancels this loop
            asyncio.create_task(self.disconnect())

    async def watchdog_loop(self):
        """Run a watchdog command at regular intervals.

        This tell us the state we need to know to decide if the chiller
        is running (including whether we have alarms).

        Start by sleeping, since `connect` runs a watchdog command.
        """
        try:
            while self.connected:
                await asyncio.sleep(self.config.watchdog_interval)
                await self.do_watchdog()
        except (asyncio.CancelledError, ConnectedError):
            self.log.debug("watchdog_loop ends")
        except Exception:
            self.log.exception("watchdog_loop failed")
            # Don't await disconnect because it cancels this loop
            asyncio.create_task(self.disconnect())
