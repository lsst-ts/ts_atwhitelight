import logging
import pymodbus
import time
import wlsExceptions

class WhiteLightSourceComponentSimulator():
    """ A fake version of the White Light Source component that doesn't
        communicate with hardware at all but prints the current wattage
        of the WLS Bulb.
    """

    def __init__(self, ip='140.252.33.160', port=502):
        self.startupWattage = 1200
        self.startupTime = 2
        self.bulbHours = None #Read this from EFD when we initialize
        self.bulbWattHours = None # This too
        self.bulbCount = None #how many bulbs have there been in total?
        self.bulbState = 0 

    def powerLightOn(self):
        """ Signals the Horiba device to power light on

            Parameters
            ----------
            None

            Returns
            -------
            None
        """
        self.bulbState = 800
        print("WLS bulb set to "+ str(self.bulbState) + " watts.")

    def powerLightOff(self):
        """ Signals the Horiba device to power light off. After
            powering off, light cannot be powered on for 5 mins

            Parameters
            ----------
            None

            Returns
            -------
            None
        """
        self.bulbState = 0
        print("WLS bulb set to "+ str(self.bulbState) + " watts.")

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
        
        self.bulbState = self.startupWattage
        print("WLS bulb set to "+ str(self.bulbState) + " watts.")
        time.sleep(self.startupTime)
        self.bulbState = watts
        print("WLS bulb set to "+ str(self.bulbState) + " watts.")
        
