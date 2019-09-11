import socket
from chillerEncoder import ChillerPacketEncoder
cpe = ChillerPacketEncoder()
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("140.252.33.70", 4001))
s.send(cpe.watchdog())
resp = s.recv(32)
import chillerModel
cm = chillerModel.ChillerModel()
cm.responder(resp)