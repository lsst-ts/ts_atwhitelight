import asyncio
import socket
import logging


class FakeChillerComponent(object):
    def __init__(self, ip, por, log):
        self.ip = ip
        self.port = port
        self.timeout = 5
        self.con = False
        self.log = log
        self.response_dict = {
            b".0103rSetTemp26\r": b"#01030rSetTemp+020038\r",
            b".0101WatchDog01\r": b"#01010WatchDog1001E8\r",
            b".0120rWarnLv1ee\r": b"#01200rWarnLv10800DB\r",
            b".0104rSupplyT46\r": b"#01040rSupplyT+028464\r",
            b".0107rReturnT3c\r": b"#01070rReturnT+012352\r",
            b".0108rAmbTemp0f\r": b"#01080rAmbTemp+031124\r",
            b".0109rProsFlo2f\r": b"#01090rProsFlo+001949\r",
            b".0110rTECB1Cr66\r": b"#01100rTECB1Cr+000177\r",
            b".0111rTECDrLvb7\r": b"#01110rTECDrLv+0000C7\r",
            b".0113rTECB2Cr6a\r": b"#01130rTECB2Cr000,C8E\r",
            b".0149rUpTime_21\r": b"#01490rUpTime_1362627A\r",
            b".0150rFanSpd1d3\r": b"#01500rFanSpd10000B8\r",
            b".0151rFanSpd2d5\r": b"#01510rFanSpd20000BA\r",
            b".0152rFanSpd3d7\r": b"#01520rFanSpd30000BC\r",
            b".0153rFanSpd4d9\r": b"#01530rFanSpd40000BE\r",
        }

    async def connect(self):
        """Connect to chiller's ethernet-to-serial bridge"""
        # self.log.debug(f"connecting to: {self.ip}:{self.port}.")
        if self.connected:
            raise RuntimeError("Already connected")
        self.con = True

    async def disconnect(self):
        self.con = False

    async def send_command(self, cmd):
        if cmd in self.response_dict:
            await asyncio.sleep(0.05)
            return self.response_dict[cmd]
        else:
            return cmd

    @property
    def connected(self):
        return self.con
