import logging
import pymodbus
import time
import wlsExceptions

class WhiteLightSourceComponentSimulator():
    """ A fake version of the White Light Source component that doesn't
        communicate with hardware at all but prints the wattage output
        of a simulated WLS Bulb.
    """

    def __init__(self, ip='140.252.33.160', port=502):
        self.startupWattage = 1200
        self.startupTime = 2
        self.defaultWattage = 800
        self.bulbHours = None #Read this from EFD when we initialize
        self.bulbWattHours = None # This too
        self.bulbCount = None #how many bulbs have there been in total?
        self.bulbState = 0 

    def setLightPower(self, watts):
        """ Sets the brightness (in watts) on the white light source.
            We always set the brightness to self.startupWattage for a
            moment (self.startupTime), then step it back down to the 
            target wattage.

            Parameters
            ----------
            watts : int or float
                Should be in the range of 800-1200 (inclusive)

            Returns
            -------
            None
        """
        
        self.bulbState = watts
        self._printBulbState()
    
    def _printBulbState(self):
        print("Simulated WLS bulb set to " + str(self.bulbState) + " watts.")

