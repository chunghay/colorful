###############################################################################
## All code excluding the websocket sections was written by Chung-Hay Luk.
##
## Raspberry Pi serves as the server for the websocket. 
## It reads in I2C data from the GPIO pins.
##
##  Copyright 2013
##  Licensed under the Apache License, Version 2.0 (the "License").
##  See below for license details.
##
## Websocket sections of the code (classes, creating factory sections) are
## modified from example code for AutobahnPython found here:
## https://github.com/tavendo/AutobahnPython/blob/master/examples/websocket/broadcast/server.py
##
##  It is licensed as such:
##
##  Copyright 2011,2012 Tavendo GmbH
##
##  Licensed under the Apache License, Version 2.0 (the "License");
##  you may not use this file except in compliance with the License.
##  You may obtain a copy of the License at
##
##      http://www.apache.org/licenses/LICENSE-2.0
##
##  Unless required by applicable law or agreed to in writing, software
##  distributed under the License is distributed on an "AS IS" BASIS,
##  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
##  See the License for the specific language governing permissions and
##  limitations under the License.
##
###############################################################################

# TODO: Make script to handle voting model. Import it here.
import json
import sys
from autobahn import websocket
from twisted.internet import reactor
from twisted.python import log


class BroadcastServerProtocol(websocket.WebSocketServerProtocol):

  def onOpen(self):
     self.factory.register(self)

  def onMessage(self, msg, binary):
     if not binary:
        # Validate that the message data is proper JSON dictionary.
        msg = validateData(msg)
        
        # Figure out if the message is from the model/sensor
        # or from the audience/webpage.
        is_sensor = authenticateSensor(msg)

        # If the message is from the model/sensor, update the webpage.
        # The LEDs will be directly controlled by Raspberry Pi.
        if is_sensor:
          print "data from sensor"
          # outputMsg = {'': }
          # Turn into string: json.dumps
          #self.factory.broadcast()

        # If the message is from an audience member, add it to the
        # voting system. Update the resulting decision color,
        # and send it to the webpage. Send it to Raspberry Pi to turn on LEDs,
        # if the model sets the dress control mode to audience.
        else:
          # Use voting model from self.factory.model
          #self.factory.broadcast("'%s' from %s" % (msg, self.peerstr))

  def connectionLost(self, reason):
     websocket.WebSocketServerProtocol.connectionLost(self, reason)
     self.factory.unregister(self)


class BroadcastServerFactory(websocket.WebSocketServerFactory):
  """
  Simple broadcast server broadcasting any message it receives to all
  currently connected clients.
  """

  def __init__(self, url, voteModel, debug = False, debugCodePaths = False):
     websocket.WebSocketServerFactory.__init__(self, url, voteModel,
                                     debug=debug, debugCodePaths=debugCodePaths)
     self.clients = []
     self.tickcount = 0
     self.tick()
     self.model = voteModel

  def tick(self):
     self.tickcount += 1
     #self.broadcast("'tick %d' from server" % self.tickcount)
     reactor.callLater(1, self.tick)

  def register(self, client):
     if not client in self.clients:
        print "registered client " + client.peerstr
        self.clients.append(client)

  def unregister(self, client):
     if client in self.clients:
        print "unregistered client " + client.peerstr
        self.clients.remove(client)

  def broadcast(self, msg):
     print "broadcasting message '%s' .." % msg
     for c in self.clients:
        c.sendMessage(msg)
        print "message sent to " + c.peerstr


def validateData(data):
  # Check that data is in proper json format.
  try:
    obj = json.loads(data)
  except ValueError:
    raise ValueError, "Invalid json data: " + data
  
  # Check object is dictionary.
  if not isinstance(obj, dict):
    raise ValueError, "Object is not a dictionary"

  return obj


# Determine if data is from the sensor as oppose to the audience.
def authenticateSensor(msg):
  expected_secret = '5a2649734c55285b24777e427e'

  if msg.has_key('id') and msg.get('id') == expected_secret:
    is_sensor = True
  else:
    is_sensor = False

  return is_sensor


def main():
  # Add fancy time logging.
  log.startLogging(sys.stdout)

  # Instantiate voting model.
  # TODO: Make separate Python script for handling the voting.
  #       Then import that script into this script.
  model = []

  # Listen to all addresses on port 9000.
  factory = BroadcastServerFactory("ws://[::]:9000", voteModel = model,
                                    debug = False)
  factory.protocol = BroadcastServerProtocol
  listenWS(factory)

  # Start handling requests across websocket.
  reactor.run()


if __name__ == '__main__':
  main()