from binascii import hexlify

__all__ = ["ChillerPacketEncoder"]

class ChillerPacketEncoder(object):
    def __init__(self):
        self.device_id = "01"


    def _checksum(self, st):
        """
        Checksum field shall be two ASCII hexadecimal bytes
        representing the sum of all previous bytes (8 bit 
        summation, no carry) of the command starting with SOC
        
        Parameters
        ----------
        st : ascii string to be checksummed

        Returns
        -------
        checksum : 2-character ascii string
        """
        total = 0x0
        for char in st:
            total = total + int(hexlify(bytes(char, "ascii")), 16)
        return hex(total)[-2:]

    def _commandwrapper(self, st):
        """
        Command packets begin with a period character and
        device ID, and end with a checksum and a return character.
        This function takes an input string
        containing the command id, command name, and
        optional data payload, and performs the checksum
        and assembles the boilerplate around it. 
        
        Parameters
        ----------
        st : 10-18 character ascii string containing
             the command ID followed by 8 chars of 
             descriptive text and 0-8 characters of
             data payload. 

        Returns
        -------
        string
    
        """

        if len(st) < 10 or len(st) > 18:
            raise Exception

        start = "." + self.device_id + st
        cs = self._checksum(start)
        outstr = start + cs + "\r"
        return bytes(outstr,'ascii')

    def _tempformatter(self, num):
        """
        The Chiller likes its tempertures as 5 character
        strings. The first character is the sign, the next
        three are the whole-number digits, and the last 
        character is a decimal digit. This function takes
        any number between -999.9 and 999.9 and puts it in
        that format. For example:
        1.29 --> '+0013'
        -20  --> '-0200'
        0.5  --> '+0005'
        
        Parameters
        ----------
        num : number to be formatted. 

        Returns
        -------
        5-character string

        """

        if num < -999.9 or num > 999.9:
            raise Exception
        if num < 0:
            sign = "-"
        else: sign = "+" 
        num = float(num)
        rtemp = round(num,1)
        tempstr = str(rtemp)

        #split the string around the decimal character
        halves = tempstr.split('.')

        #get rid of the - symbol python's string representation puts in
        if halves[0][0] == '-':
            halves[0] = halves[0][1:]
        
        #reassemble
        whole = halves[0]+halves[1]

        #pad with leading zeros
        while len(whole) < 4:
            whole = "0" + whole

        data = sign + whole
        return data

    def watchdog(self):
        """
        Command ID 01
        Generates the ascii string that requests a watchdog
        packet from the Chiller.
        
        Parameters
        ----------
        None

        Returns
        -------
        string

        """

        message = "01WatchDog"
        return self._commandwrapper(message)

    def readSupplyTemp(self):
        """
        Command ID 04
        Generates the ascii string that requests the 
        chiller's supply temperature
        
        Parameters
        ----------
        None

        Returns
        -------
        string

        """

        message = "04rSupplyT"
        return self._commandwrapper(message)

    def readReturnTemp(self):
        """
        Command ID 07
        Generates the ascii string that requests a the 
        chiller's return temperature
        
        Parameters
        ----------
        None

        Returns
        -------
        string

        """

        message = "07rReturnT"
        return self._commandwrapper(message)
    
    def readAmbientTemp(self):
        """
        Command ID 08
        Generates the ascii string that requests a the 
        ambient temperature
        
        Parameters
        ----------
        None

        Returns
        -------
        string

        """

        message = "08rAmbTemp"
        return self._commandwrapper(message)

    def readProcessFlow(self):
        """
        Command ID 09
        Generates the ascii string that requests a the 
        chiller's process flow, in liters/minute
        
        Parameters
        ----------
        None

        Returns
        -------
        string

        """

        message = "09rProsFlo"
        return self._commandwrapper(message)

    def setChillerStatus(self, status):
        """
        Command ID 15
        Generates the ascii string that sets the chiller status
        status 0 = standby
        status 1 = run
        
        Parameters
        ----------
        status : int 

        Returns
        -------
        string

        """
        if status != 0 and status != 1:
            raise Exception
        output = self._commandwrapper('15sStatus_' + str(status))
        return output

    

    def setControlTemp(self, temp):
        """
        Command ID 17
        Generates the ascii string that sets the target 
        temperature. In degrees C.
        
        Parameters
        ----------
        temp : float

        Returns
        -------
        string

        """

        data = self._tempformatter(temp)
        output = self._commandwrapper('17sCtrlTmp' + data)
        return output

    def readAlarmStateL1(self):
        """
        Command ID 18
        Generates the ascii string to read the alarm state
        
        Parameters
        ----------
        None

        Returns
        -------
        string

        """

        output = self._commandwrapper('18rAlrmLv1')
        return output

    def readAlarmStateL2(self, sublevel=1):
        """
        Command ID 19
        Generates the ascii string to read the alarm state
        For some reason there are two "levels" within level
        2... We interpret any input other than 1 as 2. 
  
        Parameters
        ----------
        sublevel : int
            which set of L2 alarms to query
            should be 1 or 2

        Returns
        -------
        string
        """
        if sublevel != 1:
            sublevel = 2
        output = self._commandwrapper('19rAlrmLv2' + str(sublevel))
        return output

    def readWarningState(self):
        """
        Command ID 20
        Generates the ascii string to read the warning state
        
        Parameters
        ----------
        None

        Returns
        -------
        string

        """

        output = self._commandwrapper('20rWarnLv1')
        return output

    def setWarning(self, warntype, value):
        """
        Command IDs 21-25
        Generates the ascii string that sets a hi/low
        temperature warning and low flow warning.
        Temperatures are Celsius and flow is liters
        per minute. Temps may be negative, but flow 
        must be positive.
        
        Parameters
        ----------
        warntype : string
            "HiSupplyTemp"
            "LowSupplyTemp"
            "HiAmbientTemp"
            "LowAmbientTemp"
            "LowProcessFlow" 
        
        value : float in range -999.9 to 999.9

        Returns
        -------
        string

        """

        if warntype == "HiSupplyTemp":
            message = "21sHiSpTWn" + self._tempformatter(value)
        elif warntype == "LowSupplyTemp":
            message = "22sLoSpTWn" + self._tempformatter(value)
        elif warntype == "HiAmbientTemp":
            message = "23sHiAmTWn" + self._tempformatter(value)
        elif warntype == "LowAmbientTemp":
            message = "24sLoAmTWn" + self._tempformatter(value)
        elif warntype == "LowProcessFlow":
            if value < 0: 
                raise Exception
            message = "25sLoPFlWn" + self._tempformatter(value)
        else:
            raise Exception
        output = self._commandwrapper(message)
        return output

    def setAlarm(self, alarmtype, value):
        """
        Command IDs 26-30
        Generates the ascii string that sets a hi/low
        temperature alarms and low flow alarm. Alarms
        are like warnings but they also trigger a 
        fault state in the CSC, which will lead to some
        action to try to safely shut things down.
        Temperatures are Celsius and flow is liters
        per minute. Temps may be negative, but flow 
        must be positive.

        
        Parameters
        ----------
        warntype : string
            "HiSupplyTemp"
            "LowSupplyTemp"
            "HiAmbientTemp"
            "LowAmbientTemp"
            "LowProcessFlow" 
        
        value : float in range -999.9 to 999.9

        Returns
        -------
        string

        """

        if alarmtype == "HiSupplyTemp":
            message = "26sHiSpTAl" + self._tempformatter(value)
        elif alarmtype == "LowSupplyTemp":
            message = "27sLoSpTAl" + self._tempformatter(value)
        elif alarmtype == "HiAmbientTemp":
            message = "28sHiAmTAl" + self._tempformatter(value)
        elif alarmtype == "LowAmbientTemp":
            message = "29sLoAmTAl" + self._tempformatter(value)
        elif alarmtype == "LowProcessFlow":
            if value < 0: 
                raise Exception
            message = "30sLoPFlAl" + self._tempformatter(value)
        else:
            raise Exception
        output = self._commandwrapper(message)
        return output

    def readFanSpeed(self, fanNumber):
        if fanNumber > 4 or fanNumber < 1: raise Exception
        cmdid = fanNumber + 49
        return self._commandwrapper(message)

    