import logging
import pymodbus
from pymodbus.client.sync import ModbusTcpClient as ModbusClient

class WhiteLightSourceComponent():

    def __init__(self, ip, port):
        self.client = ModbusClient(ip,port)

    def powerLightOn(self):
        """ Signals the Horiba device to power light on

            Parameters
            ----------
            None

            Returns
            -------
            None
        """
        pass

    def powerLightOff():
        """ Signals the Horiba device to power light off. After
            powering off, light cannot be powered on for 5 mins

            Parameters
            ----------
            None

            Returns
            -------
            None
        """
        pass

    def setLightPower(self, wattage):
        """ Sets the wattage on the white light source.

            Parameters
            ----------
            wattage : integer
                Should be in the range of 800-1200 (inclusive)

            Returns
            -------
            None
        """
        if wattage < 800 or wattage > 1200:
            raise Exception

        #y=mx+b, solve for x!
        voltage = -4.176993316101 + wattage / 130.762
        
    
    def _voltsToCounts(volts):
        """ converts volts for 12-bit ADAM-6024 output

        Parameters
        ----------
        volts : float
            voltage we want to send out on the ADAM output
        
        Returns
        -------
        counts : integer
            voltage converted into a 12 bit number for ADAM
        """

        vtc = 10/4095
        return int(volts/vtc)

    def _countsToVolts(counts):
    """ converts ADAM-6024 input readings into volts

        Parameters
        ----------
        counts : integer
            16-bit integer received from ADAM device
        
        Returns
        -------
        volts : float
            counts converted into voltage number
        """
        ctv = 20/65535
        return counts * ctv - 10