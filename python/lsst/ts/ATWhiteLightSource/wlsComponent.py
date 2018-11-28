import logging
import pymodbus
from pymodbus.client.sync import ModbusTcpClient as ModbusClient
import time
import wlsExceptions

class WhiteLightSourceComponent():
""" Class that handles communication with the white light source hardware
"""

    def __init__(self, ip='140.252.33.160', port=502):
        self.client = ModbusClient(ip,port)

    def setLightPower(self, watts):
        """ Sets the brightness (in watts) on the white light source.
            

            Parameters
            ----------
            watts : int or float
                Should be in the range of 800-1200 (inclusive)

            Returns
            -------
            None
        """
        
        targetVoltage = self._wattsToVolts(watts)
        self._writeVoltage(targetVoltage)


    def _wattsToVolts(self, watts):
        """ calculates what voltage to send (in the range of 1.961v to 5.0v)
            in order to achieve the desired watt output (in the range of 
            800w to 1200w) from the Horiba Kiloarc device.

        Parameters
        ----------
        watts : float
            desired wattage for the bulb
        
        Returns
        -------
        volts : float
            the Kiloarc's input voltage corresponding to the desired output wattage
        """

        return -4.176993316101 + watts / 130.762

    def _writeVoltage(self, volts):
        """ writes the requested voltage to the ADAM-6024 output register AO0

        Parameters
        ----------
        volts : float
            voltage we want to send out on the ADAM output
        
        Returns
        -------
        None

        """
        self.client.write_register(10,self._voltsToCounts(volts))
        
    
    def _voltsToCounts(self, volts):
        """ discretizes volts for 12-bit ADAM-6024 output

        Parameters
        ----------
        volts : float
            voltage we want to send out on the ADAM output
        
        Returns
        -------
        counts : integer
            voltage converted into a 12 bit int for ADAM
        """

        vtc = 10/4095
        return int(volts/vtc)

    def _countsToVolts(self, counts):
        """ converts discrete ADAM-6024 input readings into volts

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