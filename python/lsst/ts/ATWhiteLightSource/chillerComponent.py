import asyncio


class ChillerComponent(object):
    def __init__(self, ip, port, com_lock, log=None):
        self.ip = ip
        self.port = port
        self.connect_task = None
        self.log = None
        self.reader = None
        self.writer = None
        self.timeout = 15
        self.response_dict = {}
        self.last_response = None
        self.chiller_com_lock = com_lock

    async def connect(self):
        """Connect to chiller's ethernet-to-serial bridge"""
        # self.log.debug(f"connecting to: {self.ip}:{self.port}.")
        if self.connected:
            raise RuntimeError("Already connected")
        self.log.debug(f"Connecting to chiller @ {self.ip}")
        self.reader, self.writer = await asyncio.wait_for(
            asyncio.open_connection(self.ip, self.port), self.timeout
        )

    async def disconnect(self):
        if self.writer is not None:
            self.writer.close()
            await self.writer.wait_closed()

        del self.reader
        del self.writer

        self.reader = None
        self.writer = None

    async def send_command(self, cmd):
        """
        send a message to the chiller and return the response
        """
        if self.connected:
            async with self.chiller_com_lock:
                self.writer.write(cmd)
                response = await asyncio.wait_for(
                    self.reader.readuntil(separator=b"\r"), timeout=5
                )
                # TODO remove this eventually, it's just used to harvest data for chiller's simulation mode
                self.response_dict[cmd] = response
                return response
        else:
            raise ConnectionError("not connected")

    @property
    def connected(self):
        if None in (self.reader, self.writer):
            return False
        else:
            return True
