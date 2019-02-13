__all__ = ["WhiteLightSourceComponent"]

from pymodbus.client.sync import ModbusTcpClient as ModbusClient
from lsst.ts import salobj
import time


class WhiteLightSourceComponent():
    """ Class that handles communication with the white light source hardware
    """

    def __init__(self, ip='140.252.33.160', port=502):
        self.client = ModbusClient(ip, port)
        self.bulbHours = 0  # Read this from EFD when we initialize
        self.bulbWattHours = 0  # This too
        self.bulbCount = 0  # how many bulbs have there been in total?
        self.bulbHoursLastUpdate = time.time()/3600
        self.bulbState = 0

        self.greenStatusLED = False   # operating/standby indicator
        self.blueStatusLED = False    # cooldown indicator
        self.redStatusLED = False     # error indicator
        self.errorLED = False         # flashes to signal error type

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
        self.bulbState = watts

    def checkStatus(self):
        """ checks 4 analog inputs to see if any of them have
            voltages in excess of 3.0. If so, that's an error!

        Parameters
        ----------
        None

        Returns
        -------
        errors: List of booleans
        """

        errors = [False, False, False, False]
        for i in range(4):
            errors[i] = self._readVoltage(i) > 3.0

        return errors

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

        output = -4.176993316101 + watts / 130.762
        if output < 0: output = 0 # voltage should have a floor of 0. 
        return output

    def _readVoltage(self, channel):
        """ reads the voltage off of ADAM-6024's inputs for a given channel.

        Parameters
        ----------
        channel : int
            analog input channel to read, in range of 0-5

        Returns
        -------
        volts : float
            the voltage on this particular ADAM input channel
        """
        readout = self.client.read_input_registers(channel, 1, unit=1).registers[0]
        return self._countsToVolts(readout)

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
        self.client.write_register(10, self._voltsToCounts(volts))

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
