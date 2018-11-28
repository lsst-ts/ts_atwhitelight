from lsst.ts.ATWhiteLightSource.wlsComponent import WhiteLightSourceComponent
from lsst.ts.ATWhiteLightSource.wlsSimComponent import WhiteLightSourceComponentSimulator
import wlsExceptions
class WhiteLightSourceModel():

    def __init__(self):
        #self.component = WhiteLightSourceComponent()
        self.component = WhiteLightSourceComponentSimulator()

    def powerLightOn(self):
        self.component.powerLightOn()
    
    def powerLightOff(self):
        self.component.powerLightOff()
    
    def setLightPower(self, watts):
        if watts < 800: raise wlsExceptions.WattageTooLowException
        elif watts > 1200: raise wlsExceptions.WattageTooHighException
        else:
            self.component.setLightPower(watts)
