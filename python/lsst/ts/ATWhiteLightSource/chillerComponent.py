import asyncio
import socket
import logging


class ChillerComponent(object):
    def __init__(self):
        self.ip = "140.252.33.70"
        self.port = 4001
        self.connect_task = None
        self.reader = None
        self.writer = None
        self.timeout = 5

    async def connect(self):
        """Connect to chiller's ethernet-to-serial bridge"""
        #self.log.debug(f"connecting to: {self.ip}:{self.port}.")
        if self.connected:
            raise RuntimeError("Already connected")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip, self.port))
        self.connect_task = asyncio.open_connection(sock=s)
        self.reader, self.writer = await asyncio.wait_for(self.connect_task, self.timeout)

    async def disconnect(self):
        try:
            self.reply_handler_loop.cancel()
            await self.reply_handler_loop
        except asyncio.CancelledError:
            self.log.info("reply handler task cancelled")
        except Exception as e:
            self.log.exception(e)
        
        self.writer.close()
        
        self.reader = None
        self.writer = None

    async def send_command(self, cmd):
        """
        cmd is the ascii string of the command
        expResponse is a substring of the expected response
        that we will attempt to match against the actual response
        """

        self.writer.write(cmd)
        response = await self.reader.readuntil(separator=b'\r')
        return(response)


    @property
    def connected(self):
        if None in (self.reader, self.writer):
            return False
        else:
            return True
