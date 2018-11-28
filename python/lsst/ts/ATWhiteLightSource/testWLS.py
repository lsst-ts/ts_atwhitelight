from wlsModel import WhiteLightSourceModel

def TestPowerOn():
    model = WhiteLightSourceModel()

def TestTooHighWattage():
    model = WhiteLightSourceModel()

def TestLowWattagePowerOff():
    model = WhiteLightSourceModel()

def TestWarmUpPowerOffInterrupt(): # if we ask for < 800w during the warmup period, cancel warmup and power off
    model = WhiteLightSourceModel()

def TestWarmUpNotOtherwiseInterruptable(): # if we ask for 800-1200 watts during the warmup period, it should be ignored
    model = WhiteLightSourceModel()