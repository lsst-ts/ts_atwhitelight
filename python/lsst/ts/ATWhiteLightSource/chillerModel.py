import asyncio
from queue import Queue
from enum import IntEnum
import binascii
from chillerComponent import CHillerComponent


class ControlStatus(IntEnum):
    """ Status of the Chiller
    """
    AUTOSTART = 0 
    STANDBY = 1
    RUN = 2
    SAFETY = 3
    TEST = 4


class PumpStatus(IntEnum):
    """ Status of the Pump
    """
    PUMPOFF = 0
    PUMPON = 1


class AlarmStatus(IntEnum):
    """ Are Alarm(s) present?
    """
    NOALARM = 0
    ALARM = 1


class WarningStatus(IntEnum):
    """ Are warning(s) present?
    """
    NOWARNING = 0
    WARNING = 1


class ChillerStatus(IntEnum):
    """ Are warning(s) present?
    """
    STANDBY = 0
    RUN = 1


class Alarms():
    def __init__(self):
        self.A0 = ("Ambient Temp Sensor Alarm", "High Control Temp Alarm",
                   "PT7 High Temp Alarm", "Low Control Temp Alarm")
        self.A1 = ("Supply Temp Sensor Alarm (Latched)", "External RTD Sensor Alarm",
                   "Return Temp Sensor Alarm", "External Thermistor Sensor Alarm")
        self.A2 = ("Low Coolant Level Alarm", "Low Process Flow Alarm",
                   "Low Plant Flow Alarm", "Current Sensor 1 Alarm")
        self.A3 = ("PT7 Low Temp Alarm", "High Ambient Temp Alarm",
                   "Low Ambient Temp Alarm", "External Connector Not Installed")
        self.A4 = ("Default High Temp Alarm", "Default Low Temp Alarm",
                   "No Process Flow Alarm", "Fan Failure Alarm")
        self.A5 = ("Current Sensor 2 Alarm", "Internal 2.5v Reference Alarm",
                   "Internal 5v Reference Alarm", "System Error Alarm (global)")

        self.B0 = ("Reserved (not used)", "Reserved (not used)",
                   "Reserved (not used)", "Reserved (not used)")
        self.B1 = ("ADC System Error Alarm", "I2C System Error Alarm",
                   "EEPROM System Error Alarm", "Watchdog System Error Alarm")
        self.B2 = ("Reserved (not used)", "Reserved (not used)",
                   "Reserved (not used)", "Reserved (not used)")
        self.B3 = ("ADC Reset Error Alarm", "ADC Calibration Error Alarm",
                   "ADC Conversion Error Alarm", "Reserved (not used)")
        self.B4 = ("IO Expender Acknowledge Error Alarm", "PSA IO Expender Acknowledge Error Alarm",
                   "RTC Acknowledge Error Alarm", "Reserved (not used)")
        self.B5 = ("I2C SCL Low Error Alarm", "I2C SDA Low Error Alarm",
                   "EEPROM 1 (U201) Acknowledge Alarm", "EEPROM 2 (U200) Acknowledge Alarm")
        self.B6 = ("Reserved (not used)", "Reserved (not used)",
                   "Reserved (not used)", "Reserved (not used)")
        self.B7 = ("EEPROM 1 (U201) Read Error Alarm", "EEPROM 1 (U201) Write Error Alarm",
                   "EEPROM 2 (U200) Read Error Alarm", "EEPROM 2 (U200) Write Error Alarm")

        self.C0 = ("External RTD Sensor Open Alarm", "External RTD Sensor Short Alarm",
                   "Return Temp Sensor Open Alarm", "Return Temp Sensor Open Alarm (Maybe \
                    this should be sensor SHORT alarm? Possible typo in chiller docs)")
        self.C1 = ("Global Temp Sensor Alarm", "Supply Temp Sensor Locked Alarm",
                   "Supply Temp Sensor Open Alarm", "Supply Temp Sensor Short Alarm")
        self.C2 = ("Internal 2.5v Reference High Alarm", "Internal 2.5v Reference Low Alarm",
                   "Internal 5v Reference High Alarm", "Internal 5v Reference High Alarm", )
        self.C3 = ("External Therm Sensor Open Alarm", "External Therm Sensor Short Alarm",
                   "Ambient Temp Sensor Open Alarm", "Ambient Temp Sensor Short Alarm")
        self.C4 = ("Reserved (not used)", "Reserved (not used)", "Reserved (not used)", "Reserved (not used)")
        self.C5 = ("Current Sensor 1 Open Alarm", "Current Sensor 1 Short Alarm",
                   "Current Sensor 2 Open Alarm", "Current Sensor 2 Short Alarm")
        self.C6 = ("Rear Left Fan Noise Alarm", "Rear Right Fan Noise Alarm",
                   "Front Left Fan Noise Alarm", "Front Right Fan Noise Alarm")
        self.C6 = ("Rear Left Fan Open Alarm", "Rear Right Fan Open Alarm",
                   "Front Left Fan Open Alarm", "Front Right Fan Open Alarm")

        self.W0 = ("Low Process Flow Warning", "Process Fluid Level Warning",
                   "Switch to Supply Temp as Control Temp Warning", "Reserved (not used)")
        self.W1 = ("High Control Temp Warning", "Low Control Temp Warning",
                   "High Ambient Temp Warning", "Low Ambient Temp Warning")
        self.W2 = ("Reserved (not used)", "Reserved (not used)",
                   "Reserved (not used)", "Reserved (not used)")
        self.W3 = ("Reserved (not used)", "Reserved (not used)",
                   "Reserved (not used)", "Reserved (not used)")

        self.L1Alarms = (self.A0, self.A1, self.A2, self.A3, self.A4, self.A5)
        self.L2AlarmsPt1 = (self.B0, self.B1, self.B2, self.B3, self.B4, self.B5)
        self.L2AlarmsPt2 = (self.C0, self.C1, self.C2, self.C3, self.C4, self.C5)

        self.Warnings = (self.W0, self.W1, self.W2, self.W3)



class ChillerModel():
    def __init__(self):

        self.device_id = "01"
        self.alarms = Alarms()
        self.response_dict = {
            "01": self.watchdog_decode,
            "04": self.readSupplyTemp_decode,
            "07": self.readReturnTemp_decode,
            "08": self.readAmbientTemp_decode,
            "09": self.readProcessFlow_decode,
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
        }

        #chiller state
        self.controlStatus = None
        self.pumpStatus = None
        self.chillerStatus = None
        self.supplyTemp = None
        self.returnTemp = None
        self.ambientTemp = None
        self.processFlow = None
        self.setTemperature = None
        self.tecBank1 = None
        self.tecBank2 = None
        self.teDrive = None
        self.alarmPresent = False
        self.warningPresent = False
        self.fan1speed = None
        self.fan2speed = None
        self.fan3speed = None
        self.fan4speed = None

        asyncio.ensure_future(self.telemloop())

    def responder(self, msg):
        """
        Figure out what data is in a response and pass it along to the appropriate handling method.
        """
        msg = str(msg)
        checksum = msg[-5:-3]
        msg = msg[2:-5]
        print(msg)

        # compute checksum
        total = 0x0
        for char in msg:
            total = total + int(binascii.hexlify(bytes(char, "ascii")), 16)
        checksum_from_chiller = hex(total)[-2:]

        if checksum != checksum_from_chiller.upper():
            raise Exception

        # process the string
        if msg[0] != "#":
            print("uh oh, this doesn't look like a chiller response")
        cmd_id = msg[3:5]
        error = msg[5]
        data = msg[14:]
        response_method = self.response_dict[cmd_id]

        print("cmd_id: " + str(cmd_id))
        print("error: " + str(error))
        print("data: " + str(data))
        print("checksum: " + str(checksum_from_chiller))
        print("response method: " + str(response_method))

        response_method(data)


    def watchdog_decode(self, msg):
        #read watchdog status from chiller
        CS = ControlStatus(int(msg[0]))
        PS = PumpStatus(int(msg[1]))
        AS = AlarmStatus(int(msg[2]))
        WS = WarningStatus(int(msg[3]))

        #update model state
        self.controlStatus = CS
        self.pumpStatus = PS
        self.alarmPresent = AS
        self.warningPresent = WS

    def tempParser(self, msg):
        """
        parses temp and flowrate data into a python float.
        """
        temp = 0
        temp += int(msg[1:4])
        temp += int(msg[4])/10
        if msg[0] == "-":
            temp = 0 - temp
        return(temp)

    def readSupplyTemp_decode(self, msg):
        self.supplyTemp = self.tempParser(msg)

    def readReturnTemp_decode(self, msg):
        self.returnTemp = self.tempParser(msg)

    def readAmbientTemp_decode(self, msg):
        self.ambientTemp = self.tempParser(msg)

    def readProcessFlow_decode(self, msg):
        # flow uses the same formatting as temp
        self.processFlow = self.tempParser(msg)

    def setChillerStatus_decode(self, msg):
        SS = ChillerStatus(int(msg[0]))
        self.chillerStatus = SS

    def setControlTemp_decode(self, msg):
        pass

    def readAlarmStateL1_decode(self, msg):
        alarmList = []
        for i in range(6):
            val = int(msg[i], 16)
            mask = self._sorter(val)
            for j in range(4):
                if mask[j]:
                    alarmList.append(self.alarms.L1Alarms[i][j])

        print(alarmList)
 
    def readAlarmStateL2_decode(self, msg):
        print(msg)
        alarmList = []
        for i in range(8):
            val = int(msg[i+1], 16)
            mask = self._sorter(val)
            for j in range(4):
                if mask[j]:
                    if msg[0] == "1":
                        alarmList.append(self.alarms.L2AlarmsPt1[i+1][j])
                    elif msg[0] == "2":
                        alarmList.append(self.alarms.L2AlarmsPt2[i+1][j])

        print(alarmList)

    def readWarningState_decode(self, msg):
        warningList = []
        for i in range(4):
            val = int(msg[i], 16)
            mask = self._sorter(val)
            for j in range(4):
                if mask[j]:
                    warningList.append(self.alarms.Warnings[i][j])

        print(warningList)
        

    def setWarning_decode(self, msg):
        pass

    def setAlarm_decode(self, msg):
        pass

    def readFanSpeed_decode(self, msg):
        pass

    async def telem_gather(self):
        """
        Queries the chiller for all the telemetry we need to publish, and let's us know when it's done. 
        """
        telem_task = asyncio.Future()
        telem_task.set_result(None)

    def _sorter(self, num):
        """
        Takes a number and returns a 4-bit binary representation in the form of a tuple of zeroes and ones
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