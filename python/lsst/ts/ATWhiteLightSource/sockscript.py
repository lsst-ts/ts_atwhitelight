import socket
import time
from chillerEncoder import ChillerPacketEncoder

cpe = ChillerPacketEncoder()
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(('140.252.33.70', 4001))
message = cpe.readFanSpeed(1)
s.send(message)
while True:
    response = s.recv(32)
    print(response)
    break

