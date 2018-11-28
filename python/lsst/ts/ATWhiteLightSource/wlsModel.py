from lsst.ts.ATWhiteLightSource.wlsComponent import WhiteLightSourceComponent
from lsst.ts.ATWhiteLightSource.wlsSimComponent import WhiteLightSourceComponentSimulator
import wlsExceptions
import time

class WhiteLightSourceModel():

    def __init__(self):
        #self.component = WhiteLightSourceComponent()
        self.component = WhiteLightSourceComponentSimulator()
        self.startupWattage = 1200
        self.defaultWattage = 800
        self.startupTime = 2
        self.bulbHours = None #Read this from EFD when we initialize
        self.bulbWattHours = None # This too
        self.bulbCount = None #how many bulbs have there been in total?

    def powerLightOn(self):
        """ Signals the Horiba device to power light on.
            We always set the brightness to self.startupWattage for a
            moment (self.startupTime), then step it back down to the 
            default. 

            Parameters
            ----------
            None

            Returns
            -------
            None
        """
        self.component.setLightPower(self.startupWattage)
        time.sleep(self.startupTime)
        self.component.setLightPower(self.defaultWattage)
    
    def powerLightOff(self):
        self.component.setLightPower(0)
    
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
        if watts > 1200: raise wlsExceptions.WattageTooHighException
        else:
            self.component.setLightPower(watts)
