import asyncio
import time
from queue import PriorityQueue
from enum import IntEnum
import binascii
from .chillerComponent import ChillerComponent
from .fakeChillerComponent import FakeChillerComponent
from .chillerEncoder import ChillerPacketEncoder


class ControlStatus(IntEnum):
    """Status of the Chiller"""

    AUTOSTART = 0
    STANDBY = 1
    RUN = 2
    SAFETY = 3
    TEST = 4


class PumpStatus(IntEnum):
    """Status of the Pump"""

    PUMPOFF = 0
    PUMPON = 1


class AlarmStatus(IntEnum):
    """Are Alarm(s) present?"""

    NOALARM = 0
    ALARM = 1


class DriveMode(IntEnum):
    """ARe we heating or cooling"""

    COOLMODE = 0
    HEATMODE = 1


class WarningStatus(IntEnum):
    """Are warning(s) present?"""

    NOWARNING = 0
    WARNING = 1


class ChillerStatus(IntEnum):
    """Are warning(s) present?"""

    STANDBY = 0
    RUN = 1


class Alarms:
    def __init__(self):
        self.A0 = (
            "Ambient Temp Sensor Alarm",
            "High Control Temp Alarm",
            "PT7 High Temp Alarm",
            "Low Control Temp Alarm",
        )
        self.A1 = (
            "Supply Temp Sensor Alarm (Latched)",
            "External RTD Sensor Alarm",
            "Return Temp Sensor Alarm",
            "External Thermistor Sensor Alarm",
        )
        self.A2 = (
            "Low Coolant Level Alarm",
            "Low Process Flow Alarm",
            "Low Plant Flow Alarm",
            "Current Sensor 1 Alarm",
        )
        self.A3 = (
            "PT7 Low Temp Alarm",
            "High Ambient Temp Alarm",
            "Low Ambient Temp Alarm",
            "External Connector Not Installed",
        )
        self.A4 = (
            "Default High Temp Alarm",
            "Default Low Temp Alarm",
            "No Process Flow Alarm",
            "Fan Failure Alarm",
        )
        self.A5 = (
            "Current Sensor 2 Alarm",
            "Internal 2.5v Reference Alarm",
            "Internal 5v Reference Alarm",
            "System Error Alarm (global)",
        )

        self.B0 = (
            "Reserved (not used)",
            "Reserved (not used)",
            "Reserved (not used)",
            "Reserved (not used)",
        )
        self.B1 = (
            "ADC System Error Alarm",
            "I2C System Error Alarm",
            "EEPROM System Error Alarm",
            "Watchdog System Error Alarm",
        )
        self.B2 = (
            "Reserved (not used)",
            "Reserved (not used)",
            "Reserved (not used)",
            "Reserved (not used)",
        )
        self.B3 = (
            "ADC Reset Error Alarm",
            "ADC Calibration Error Alarm",
            "ADC Conversion Error Alarm",
            "Reserved (not used)",
        )
        self.B4 = (
            "IO Expender Acknowledge Error Alarm",
            "PSA IO Expender Acknowledge Error Alarm",
            "RTC Acknowledge Error Alarm",
            "Reserved (not used)",
        )
        self.B5 = (
            "I2C SCL Low Error Alarm",
            "I2C SDA Low Error Alarm",
            "EEPROM 1 (U201) Acknowledge Alarm",
            "EEPROM 2 (U200) Acknowledge Alarm",
        )
        self.B6 = (
            "Reserved (not used)",
            "Reserved (not used)",
            "Reserved (not used)",
            "Reserved (not used)",
        )
        self.B7 = (
            "EEPROM 1 (U201) Read Error Alarm",
            "EEPROM 1 (U201) Write Error Alarm",
            "EEPROM 2 (U200) Read Error Alarm",
            "EEPROM 2 (U200) Write Error Alarm",
        )

        self.C0 = (
            "External RTD Sensor Open Alarm",
            "External RTD Sensor Short Alarm",
            "Return Temp Sensor Open Alarm",
            "Return Temp Sensor Open Alarm (Maybe \
                    this should be sensor SHORT alarm? \
                        Possible typo in chiller docs)",
        )
        self.C1 = (
            "Global Temp Sensor Alarm",
            "Supply Temp Sensor Locked Alarm",
            "Supply Temp Sensor Open Alarm",
            "Supply Temp Sensor Short Alarm",
        )
        self.C2 = (
            "Internal 2.5v Reference High Alarm",
            "Internal 2.5v Reference Low Alarm",
            "Internal 5v Reference High Alarm",
            "Internal 5v Reference High Alarm",
        )
        self.C3 = (
            "External Therm Sensor Open Alarm",
            "External Therm Sensor Short Alarm",
            "Ambient Temp Sensor Open Alarm",
            "Ambient Temp Sensor Short Alarm",
        )
        self.C4 = (
            "Reserved (not used)",
            "Reserved (not used)",
            "Reserved (not used)",
            "Reserved (not used)",
        )
        self.C5 = (
            "Current Sensor 1 Open Alarm",
            "Current Sensor 1 Short Alarm",
            "Current Sensor 2 Open Alarm",
            "Current Sensor 2 Short Alarm",
        )
        self.C6 = (
            "Rear Left Fan Noise Alarm",
            "Rear Right Fan Noise Alarm",
            "Front Left Fan Noise Alarm",
            "Front Right Fan Noise Alarm",
        )
        self.C7 = (
            "Rear Left Fan Open Alarm",
            "Rear Right Fan Open Alarm",
            "Front Left Fan Open Alarm",
            "Front Right Fan Open Alarm",
        )

        self.W0 = (
            "Low Process Flow Warning",
            "Process Fluid Level Warning",
            "Switch to Supply Temp as Control Temp Warning",
            "Reserved (not used)",
        )
        self.W1 = (
            "High Control Temp Warning",
            "Low Control Temp Warning",
            "High Ambient Temp Warning",
            "Low Ambient Temp Warning",
        )
        self.W2 = (
            "Reserved (not used)",
            "Reserved (not used)",
            "Reserved (not used)",
            "Reserved (not used)",
        )
        self.W3 = (
            "Reserved (not used)",
            "Reserved (not used)",
            "Reserved (not used)",
            "Reserved (not used)",
        )

        self.L1Alarms = (self.A0, self.A1, self.A2, self.A3, self.A4, self.A5)
        self.L2Alarms1 = (self.B0, self.B1, self.B2, self.B3, self.B4, self.B5)
        self.L2Alarms2 = (self.C0, self.C1, self.C2, self.C3, self.C4, self.C5)

        self.Warnings = (self.W0, self.W1, self.W2, self.W3)


class ChillerModel:
    def __init__(self, log):

        self.config = None
        self.log = log
        self.device_id = "01"
        self.alarms = Alarms()
        self.response_dict = {
            "01": self.watchdog_decode,
            "03": self.readSetTemp_decode,
            "04": self.readSupplyTemp_decode,
            "07": self.readReturnTemp_decode,
            "08": self.readAmbientTemp_decode,
            "09": self.readProcessFlow_decode,
            "10": self.readTECBank1_decode,
            "11": self.readTECBank2_decode,
            "13": self.readTEDriveLevel_decode,
            "15": self.setChillerStatus_decode,
            "17": self.setControlTemp_decode,
            "18": self.readAlarmStateL1_decode,
            "19": self.readAlarmStateL2_decode,
            "20": self.readWarningState_decode,
            "21": self.setWarning_decode,
            "22": self.setWarning_decode,
            "23": self.setWarning_decode,
            "24": self.setWarning_decode,
            "25": self.setWarning_decode,
            "26": self.setAlarm_decode,
            "27": self.setAlarm_decode,
            "28": self.setAlarm_decode,
            "29": self.setAlarm_decode,
            "30": self.setAlarm_decode,
            "49": self.readUptime_decode,
            "50": self.readFanSpeed_decode,
            "51": self.readFanSpeed_decode,
            "52": self.readFanSpeed_decode,
            "53": self.readFanSpeed_decode,
        }

        self.q = PriorityQueue()
        self.disconnected = False
        self.component = None
        self.cpe = ChillerPacketEncoder()
        self.run_watchdog = False
        self.queueLoopBool = False
        self.queue_task = None
        self.watchdog_task = None

        # chiller state
        self.chiller_com_lock = asyncio.Lock()
        self.controlStatus = None
        self.pumpStatus = None
        self.chillerStatus = None
        self.setTemp = None
        self.supplyTemp = None
        self.returnTemp = None
        self.ambientTemp = None
        self.processFlow = None
        self.tecBank1 = None
        self.tecBank2 = None
        self.teDrivePct = None
        self.teDriveMode = None
        self.alarmPresent = False
        self.warningPresent = False
        self.fan1speed = 0
        self.fan2speed = 0
        self.fan3speed = 0
        self.fan4speed = 0
        self.chillerUptime = None
        self.l1AlarmsPresent = []
        self.l2AlarmsPresent = []
        self.l1AlarmsHex = None
        self.l2AlarmsHex = None
        self.warnings = []

    def __str__(self):
        output = (
            f"Control Status: {self.controlStatus}"
            + f", Pump Status: {self.pumpStatus}"
            + f", Chiller Status: {self.chillerStatus}"
            + f", Set Temp: {self.setTemp}"
            + f", Supply Temp: {self.supplyTemp}"
            + f", Return Temp: {self.returnTemp}"
            + f", Ambient Temp: {self.ambientTemp}"
            + f", Process Flow: {self.processFlow}"
            + f", TEC Bank 1: {self.tecBank1}"
            + f", TEC Bank 2: {self.tecBank2}"
            + f", TE Drive Level: {self.teDrivePct}"
            + f", TE Drive Mode: {self.teDriveMode}"
            + f", Fan1 Speed: {self.fan1speed}"
            + f", Fan2 Speed: {self.fan2speed}"
            + f", Fan3 Speed: {self.fan3speed}"
            + f", Fan4 Speed: {self.fan4speed}"
            + f", Uptime: {self.chillerUptime}"
        )

        return output

    async def connect(self, ip, port, sim_mode):
        """
        connect to the chiller and start the background tasks that keep the
        model up-to-date
        """
        if sim_mode:
            self.log.debug("creating simulation component")
            self.component = FakeChillerComponent(ip, port, self.chiller_com_lock, self.log)
        else:
            self.log.debug("creating real component")
            comlock = self.chiller_com_lock
            self.component = ChillerComponent(ip, port, comlock, self.log)
        await self.component.connect()
        self.run_watchdog = True
        self.queueLoopBool = True
        self.disconnected = False
        asyncio.create_task(self.queueloop())
        asyncio.create_task(self.watchdogloop())

    async def disconnect(self):
        """
        disconnect from chiller and halt loops
        """
        self.run_watchdog = False
        self.queueLoopBool = False
        await asyncio.sleep(1)
        if self.queue_task is not None:
            self.queue_task.cancel()
        if self.watchdog_task is not None:
            self.watchdog_task.cancel()
        if self.component is not None:
            await self.component.disconnect()
            self.component.reader = None
            self.component.writer = None
        self.disconnected = True

    async def apply_warnings_and_alarms(self, config):
        msgs = []
        msgs.append(self.cpe.setWarning("HiSupplyTemp", config.chiller_high_supply_temp_warning))
        msgs.append(self.cpe.setWarning("LowSupplyTemp", config.chiller_low_supply_temp_warning))
        msgs.append(self.cpe.setWarning("HiAmbientTemp", config.chiller_high_ambient_temp_warning))
        msgs.append(self.cpe.setWarning("LowAmbientTemp", config.chiller_low_ambient_temp_warning))
        msgs.append(self.cpe.setWarning("LowProcessFlow", config.chiller_low_process_flow_warning))

        msgs.append(self.cpe.setAlarm("HiSupplyTemp", config.chiller_high_supply_temp_alarm))
        msgs.append(self.cpe.setAlarm("LowSupplyTemp", config.chiller_low_supply_temp_alarm))
        msgs.append(self.cpe.setAlarm("HiAmbientTemp", config.chiller_high_ambient_temp_alarm))
        msgs.append(self.cpe.setAlarm("LowAmbientTemp", config.chiller_low_ambient_temp_alarm))
        msgs.append(self.cpe.setAlarm("LowProcessFlow", config.chiller_low_process_flow_alarm))

        for msg in msgs:
            self.q.put((1, msg))

    async def setControlTemp(self, temp):
        msg = self.cpe.setControlTemp(temp)
        self.q.put((0, msg))

    async def startChillin(self):
        msg = self.cpe.setChillerStatus(1)
        self.q.put((0, msg))

    async def stopChillin(self):
        msg = self.cpe.setChillerStatus(0)
        self.q.put((0, msg))

    def responder(self, msg):
        """
        Figure out what data is in a response and pass it along
        to the appropriate handling method.
        """
        msg = str(msg)
        checksum = msg[-5:-3]
        msg = msg[2:-5]

        # compute checksum
        total = 0x0
        for char in msg:
            total = total + int(binascii.hexlify(bytes(char, "ascii")), 16)
        checksum_from_chiller = hex(total)[-2:]

        if checksum != checksum_from_chiller.upper():
            raise Exception

        # process the string
        if msg[0] != "#":
            self.log.debug(f"{msg} is not a proper chiller response")
        cmd_id = msg[3:5]
        error = msg[5]
        data = msg[14:]
        response_method = self.response_dict[cmd_id]

        self.log.debug(
            "received chiller packet: cmd_id: "
            + str(cmd_id)
            + "; error: "
            + str(error)
            + "; data: "
            + str(data)
            + "; checksum: "
            + str(checksum_from_chiller)
            + "; response method: "
            + str(response_method.__name__)
        )

        # special case for fans: msg[13] is the fan number.
        if int(cmd_id) in (50, 51, 52, 53):
            response_method(int(msg[13]), data)
        else:
            response_method(data)

    def watchdog_decode(self, msg):
        # read watchdog status from chiller
        CS = ControlStatus(int(msg[0]))
        PS = PumpStatus(int(msg[1]))
        AS = AlarmStatus(int(msg[2]))
        WS = WarningStatus(int(msg[3]))

        # update model state
        self.controlStatus = CS
        self.pumpStatus = PS
        self.alarmPresent = AS
        self.warningPresent = WS

        # if watchdog tells us something is wrong,
        # figure out what it is with a high priority
        if self.alarmPresent:
            self.q.put((0, self.cpe.readAlarmStateL1()))
            self.q.put((0, self.cpe.readAlarmStateL2()))

        if self.warningPresent:
            self.q.put((0, self.cpe.readWarningState()))

    async def priority_watchdog(self):
        """
        sends a high priority watchdog, which will make sure the chiller state
        is up to date before we do something like turning on the kiloarc.
        We want to know if there are alarms present before we do that.
        """
        self.q.put((0, self.cpe.watchdog()))

    def tempParser(self, msg):
        """
        parses temp and flowrate data into a python float.
        """
        return int(msg) / 10

    def tecBankParser(self, msg):
        """
        parses tec bank amps dc into a python float.
        """
        return int(msg) / 1000

    def readSetTemp_decode(self, msg):
        self.setTemp = self.tempParser(msg)

    def readSupplyTemp_decode(self, msg):
        self.supplyTemp = self.tempParser(msg)

    def readReturnTemp_decode(self, msg):
        self.returnTemp = self.tempParser(msg)

    def readAmbientTemp_decode(self, msg):
        self.ambientTemp = self.tempParser(msg)

    def readProcessFlow_decode(self, msg):
        # flow uses the same formatting as temp
        self.processFlow = self.tempParser(msg)

    def readTECBank1_decode(self, msg):
        self.tecBank1 = self.tecBankParser(msg)

    def readTECBank2_decode(self, msg):
        self.tecBank2 = self.tecBankParser(msg)

    def readTEDriveLevel_decode(self, msg):
        pct = int(msg[:3]) / 100
        if msg[4] == "H":
            self.teDriveMode = DriveMode(1)
        elif msg[4] == "C":
            self.teDriveMode = DriveMode(0)
        self.teDrivePct = pct

    def setChillerStatus_decode(self, msg):
        SS = ChillerStatus(int(msg[0]))
        self.chillerStatus = SS

    def setControlTemp_decode(self, msg):
        self.setTemp = self.tempParser(msg)

    def readAlarmStateL1_decode(self, msg):
        self.l1AlarmsHex = msg
        alarmList = []
        for i in range(6):
            val = int(msg[i], 16)
            mask = self._sorter(val)
            for j in range(4):
                if mask[j]:
                    alarmList.append(self.alarms.L1Alarms[i][j])
        self.l1AlarmsPresent = alarmList

    def readAlarmStateL2_decode(self, msg):
        self.l2AlarmsHex = msg
        alarmList = []
        for i in range(8):
            val = int(msg[i + 1], 16)
            mask = self._sorter(val)
            for j in range(4):
                if mask[j]:
                    if msg[0] == "1":
                        alarmList.append(self.alarms.L2Alarms1[i + 1][j])
                    elif msg[0] == "2":
                        alarmList.append(self.alarms.L2Alarms2[i + 1][j])
        self.l2AlarmsPresent = alarmList

    def readWarningState_decode(self, msg):
        warningList = []
        for i in range(4):
            val = int(msg[i], 16)
            mask = self._sorter(val)
            for j in range(4):
                if mask[j]:
                    warningList.append(self.alarms.Warnings[i][j])

        self.warnings = warningList

    def setWarning_decode(self, msg):
        pass

    def setAlarm_decode(self, msg):
        pass

    def readUptime_decode(self, msg):
        self.chillerUptime = int(msg)

    def readFanSpeed_decode(self, fanNum, msg):
        if fanNum == 1:
            self.fan1speed = int(msg)
        elif fanNum == 2:
            self.fan2speed = int(msg)
        elif fanNum == 3:
            self.fan3speed = int(msg)
        elif fanNum == 4:
            self.fan4speed = int(msg)

    async def queueloop(self):
        """
        queue for sending commands to chiller. Telemetry is the
         lowest priority, and only gets added to the queue
        when it's empty. Watchdog commands, which report basic
        status, warnings, and alarms) are higher priority.
        commands from SAL are the highest priority and always
        jump to the front of the queue. Chiller docs say
        it can only accept 1 TCP message per second, which is
         clearly not the case, but we're sticking to their
        specs anyway...
        """
        while self.queueLoopBool:
            if self.q.empty():
                self.q.put((2, self.cpe.readFanSpeed(1)))
                self.q.put((2, self.cpe.readFanSpeed(2)))
                self.q.put((2, self.cpe.readFanSpeed(3)))
                self.q.put((2, self.cpe.readFanSpeed(4)))
                self.q.put((2, self.cpe.readSetTemp()))
                self.q.put((2, self.cpe.readSupplyTemp()))
                self.q.put((2, self.cpe.readReturnTemp()))
                self.q.put((2, self.cpe.readAmbientTemp()))
                self.q.put((2, self.cpe.readProcessFlow()))
                self.q.put((2, self.cpe.readTEDriveLevel()))
                self.q.put((2, self.cpe.readTECBank1()))
                self.q.put((2, self.cpe.readTECBank2()))
                self.q.put((2, self.cpe.readUptime()))

            pop = self.q.get()
            try:
                command = pop[1]
                resp = await self.component.send_command(command)
            except asyncio.TimeoutError:
                self.log.debug(f"Timed out waiting for chiller response to {str(command)}")
                await self.component.disconnect()
                self.disconnected = True

            # all actions taken in response to messages from
            #  the chiller are handled by responder
            self.responder(resp)
            await asyncio.sleep(1)

    async def watchdogloop(self):
        """
        Every 7 seconds, throw a watchdog on the queue. This is the one
        that will let us know if there are any warnings or alerts, so
        we check it more frequently than other telemetry.
        """

        while self.run_watchdog:
            self.q.put((1, self.cpe.watchdog()))
            await asyncio.sleep(7)

    async def reconnect_loop(self, timelimit=120):
        """this method is unused currently,
        couldn't get it working for some reason"""

        endTime = time.time() + timelimit
        self.log.debug("starting chiller reconnect")
        async with self.chiller_com_lock:
            self.log.debug("reconnect COM LOCK starts")

            while time.time() < endTime:
                await asyncio.sleep(1)
                difference = str(endTime - time.time())
                self.log.debug("attempting reconnect" + difference)
                if self.component.connected:
                    self.log.debug("SUCCESS??")
                    break
                else:
                    try:
                        await self.disconnect()
                        await self.connect(self.config.chiller_ip, self.config.chiller_port)
                        self.log.debug("\tconnected!")
                    except asyncio.TimeoutError:
                        self.log.debug("TIMED OUT")
                    except TimeoutError:
                        self.log.debug("passed timeout exception")
                    except Exception as e:
                        self.log.debug("passed another exception")
                        self.log.debug(e)
            self.log.debug("reconnect COM LOCK ends")
        self.log.debug("COULDNT RECON")

    def _sorter(self, num):
        """
        Takes a number 0-15 and returns a 4-bit binary
        representation in the form of a tuple of zeroes
        and ones. Used to decode error messages from chiller.
        """
        if num > 15:
            raise Exception

        pos4 = num // 8
        num = num % 8
        pos3 = num // 4
        num = num % 4
        pos2 = num // 2
        num = num % 2
        pos1 = num
        return (pos1, pos2, pos3, pos4)
