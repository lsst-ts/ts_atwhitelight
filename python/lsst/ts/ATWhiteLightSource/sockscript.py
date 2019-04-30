import socket
import time

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(('140.252.33.70', 4001))
message = bytes(".0101WatchDog01\r", "ascii")
s.send(message)
while True:
    response = s.recv(32)
    print(response)

