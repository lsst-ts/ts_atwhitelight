import asyncio
from queue import Queue
from enum import IntEnum
import binascii


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




class ChillerModel():
    def __init__(self):

        self.device_id = "01"
        self.response_dict = {
            "01": self.watchdog_decode,
            "04": self.readSupplyTemp_decode,
            "07": self.readReturnTemp_decode,
            "08": self.readAmbientTemp_decode,
            "09": self.readProcessFlow_decode,
            "15": self.setChillerStatus_decode,
            "17": self.setControlTemp_decode,
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
        #flow uses the same formatting as temp
        self.processFlow = self.tempParser(msg)

    def setChillerStatus_decode(self, msg):
        SS = ChillerStatus(int(msg[0]))
        self.chillerStatus = SS

    def setControlTemp_decode(self, msg):
        pass

    def setWarning_decode(self, msg):
        pass

    def setAlarm_decode(self, msg):
        pass

    def readFanSpeed_decode(self, msg):
        pass

    async def telemloop(self):
        pass