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
        self.component.setLightPower(0)
    
    def setLightPower(self, watts):
        if watts > 1200: raise wlsExceptions.WattageTooHighException
        else:
            self.component.setLightPower(watts)
