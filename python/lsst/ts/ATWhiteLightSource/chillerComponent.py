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
        self.response_dict = {}

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
        send a message to the chiller and return the response
        """

        self.writer.write(cmd)

        # response = asynico.wait_for(self.reader.readuntil(separator=b'\r'), timeout = 5)
        response = await self.reader.readuntil(separator=b'\r')

        # TODO remove this eventually, it's just used to harvest data for chiller's simulation mode
        self.response_dict[cmd] = response
        
        return(response)


    @property
    def connected(self):
        if None in (self.reader, self.writer):
            return False
        else:
            return True
