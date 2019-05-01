__all__ = ["ChillerResponseProcessor"]

class ChillerResponseProcessor(object):

    def __init__(self):
        self.device_id = "01"
        responderDict = {
            '01' : self.watchdog
            '02' : self.readControlSensor
            '03' : self.readSetTemp
            '04' : self.readSupplyTemp
            '07' : self.readReturnTemp
            '08' : self.readAmbientTemp
            '09' : self.readProcessFlow
            '10' : self.readTECBank1Current
            '11' : self.readTECBank2Current
            '13' : self.readTEDriveLevel
            '15' : self.setChillerStatus
            '16' : self.setControlSensor
            '17' : self.setControlTemp
            '18' : self.readAlarmStateL1
            '19' : self.readAlarmStateL2
            '20' : self.readWarningState
            '21' : self.setWarning
            '22' : self.setWarning
            '23' : self.setWarning
            '24' : self.setWarning
            '25' : self.setWarning
            '26' : self.setAlarm
            '27' : self.setAlarm
            '28' : self.setAlarm
            '29' : self.setAlarm
            '30' : self.setAlarm
            


        }


    def checksumcheck(self, message):
        """
        makes sure the checksum is correct. If not, resend 
        command.
        """
        pass 
    def sorter(self, message):
        """
        given the a response string from the chiller,
        this method identifies the command ID it is a
        response to, passes the message to the appropriate
        helper method to extract the relevant information
        from the packet.
        """
        
        responderDict[message[2:4]](message)

    def watchdog(self, message)