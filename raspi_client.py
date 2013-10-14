###############################################################################
## All code excluding the websocket sections was written by Chung-Hay Luk.
##
## Raspberry Pi serves as the client for the websocket.
## It reads in I2C data from the GPIO pins. It also sends data to GPIO pins
## designated as output pins.
##
##  Copyright 2013
##  Licensed under the Apache License, Version 2.0 (the "License").
##  See below for license details.
##
## Websocket sections of the code (classes, creating factory sections) are
## modified from example code for AutobahnPython found here:
## https://github.com/tavendo/AutobahnPython/blob/master/examples/websocket/broadcast/client.py
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

import RPi.GPIO as GPIO
import argparse
import json
import serial
import smbus
import sys
import threading
import time
from autobahn import websocket
from twisted.internet import reactor
from twisted.python import log


class DataClientProtocol(websocket.WebSocketClientProtocol):
  """
  Simple client that connects to a WebSocket server, sends data, and prints everything it receives.
  """

  def onConnect(self, connectionResponse):
    print 'protocol onConnect'
    self.factory.register(self, connectionResponse)

  def onMessage(self, msg, binary):
    print "Got message: " + msg
    if not binary:
       # Validate that the message data is proper JSON dictionary with desired
       # keys.
       msg = validateData(msg)
       if msg:
         visualizeData(msg)


class DataClientFactory(websocket.WebSocketClientFactory):
  """
  Simple client broadcasting any message from Raspberry Pi to its
  currently connected server.
  """

  def __init__(self, url, debug = True, debugCodePaths = False):
    websocket.WebSocketClientFactory.__init__(self, url,
                                   debug=debug, debugCodePaths=debugCodePaths)
    self.server = None

  def register(self, server, response):
    print "registered server " + response.peerstr
    self.server = server

  def unregister(self, server):
    print "unregistered server"
    self.server = None

  def clientConnectionFailed(self, connector, reason):
    print "connection failed: " + str(reason)

  def clientConnectionLost(self, connector, reason):
    print "connection lost: " + str(reason)

  def broadcast(self, msg):
    print "broadcasting message: %s" % msg
    print self.server
    if self.server is not None:
      self.server.sendMessage(msg)


class rgbChannelObject:
  # Default values of rgb channel values are 0 (no LEDs turned on).
  red = 0
  green = 0
  blue = 0


# Open I2C connection.
def openI2CBus():
  bus = smbus.SMBus(1)
  # I2C address 0x29
  # Register 0x12 has device ver. 
  # Register addresses must be OR'ed with 0x80
  bus.write_byte(0x29,0x80|0x12)
  ver = bus.read_byte(0x29)
  # version # should be 0x44
  if ver == 0x44:
    print "Device found\n"
    bus.write_byte(0x29, 0x80|0x00) # 0x00 = ENABLE register
    bus.write_byte(0x29, 0x01|0x02) # 0x01 = Power on, 0x02 RGB sensors enabled
    bus.write_byte(0x29, 0x80|0x14) # Reading results start register 14, LSB then MSB
    return bus
  else:
    print "Device not found\n"


# Read I2C data.
def readI2CData(i2c_input, factory, channelObject, idString):
  while True:
    data = i2c_input.read_i2c_block_data(0x29, 0)
    clear = clear = data[1] << 8 | data[0]
    red = data[3] << 8 | data[2]
    green = data[5] << 8 | data[4]
    blue = data[7] << 8 | data[6]
    crgb = "clear: %s, red: %s, green: %s, blue: %s\n" % (clear, red, green, blue)
    #print crgb

    # Turn raw data into hex code for visualization.
    thesum = red + green + blue
    if thesum == 0:
      r = 0
      g = 0
      b = 0
    else:
      r = round(float(red) / float(thesum) * 256)
      g = round(float(green) / float(thesum) * 256)
      b = round(float(blue) / float(thesum) * 256)
    hexrgb = "{\"id\": \"%s\", \"clear\": %d, \"red\": %d, \"green\": %d, \"blue\": %d}" % (idString, clear, r, g, b)
    #print hexrgb

    # Calculate PWM values for visualizing rgb values in rgb LED output.
    dcR = 1 - float(r) / float(256)
    dcG = 1 - float(g) / float(256)
    dcB = 1 - float(b) / float(256)

    # Ensure that duty cycle (dc) range is 0.0 <= dcX <= 100.0.
    dcR = sorted([0, dcR, 100])[1]
    dcG = sorted([0, dcG, 100])[1]
    dcB = sorted([0, dcB, 100])[1]
    print "Duty cycles: %.2f, %.2f, %.2f\n" % (1 - dcR, 1 - dcG, 1 - dcB)

    channelObject.red.ChangeDutyCycle(dcR)
    channelObject.green.ChangeDutyCycle(dcG)
    channelObject.blue.ChangeDutyCycle(dcB)

    time.sleep(1)

    # Check that data is formatted correctly.
    try:
      obj = validateData(hexrgb)
    except ValueError, e:
      print e
    else:
      # Send json data as string for websocket.
      factory.broadcast(json.dumps(obj))

  else:
    print "I2C connected device not found\n"
    
    channelObject.red.stop()
    channelObject.green.stop()
    channelObject.blue.stop()
    GPIO.cleanup()


# Validate data.
def validateData(data):
  # Check that data is in proper json format.
  try:
    obj = json.loads(data)
  except ValueError:
    raise ValueError, "Invalid json data: " + data

  # Check object is dictionary.
  if not isinstance(obj, dict):
    raise ValueError, "Object is not a dictionary"

  # Validate desired keys in object.
  keys = ('clear', 'red', 'green', 'blue')
  missing_keys = []
  for key in keys:
    if key not in obj:
      missing_keys.append(key)

  if missing_keys:
    raise ValueError, "Missing keys: %s" % missing_keys

  # Validate values of desired keys are integers.
  for key, value in obj.iteritems():
    if key != 'id':
      if not isinstance(value, int):
        raise ValueError, "Value for %s is not an integer: %s. Its type: %s" % (key, value, type(value))

  return obj


def visualizeData(data):
  print 'visualize data'


def setupPWM(rPin, gPin, bPin):
  GPIO.setmode(GPIO.BOARD)
  GPIO.setup(rPin, GPIO.OUT)
  GPIO.setup(gPin, GPIO.OUT)
  GPIO.setup(bPin, GPIO.OUT)

  pR = GPIO.PWM(rPin, 0.1) # channel, frequency (Hz). Don't initiate freq. as 0
  pG = GPIO.PWM(gPin, 0.1) # channel, frequency (Hz)
  pB = GPIO.PWM(bPin, 0.1) # channel, frequency (Hz)

  pR.start(0)
  pG.start(0)
  pB.start(0)
  
  channelObj = rgbChannelObject()
  channelObj.red = pR
  channelObj.green = pG
  channelObj.blue = pB
  
  return channelObj


# Get input arguments.
def getArguments():
  # Enable parsing of arguments for this script.
  parser = argparse.ArgumentParser(description=
                      'Set settings for running this script.')
  parser.add_argument('-a', '--address',
                      default='ws://ec2-54-200-22-181.us-west-2.compute.amazonaws.com',
                      help='address of WebSocket server (default: ws://ec2-54-200-22-181.us-west-2.compute.amazonaws.com  It''s the Amazon cloud instance for Project Nunway)')
  parser.add_argument('-p', '--port_number', type=int,
                      default=9000,
                      help='port number of server (default: 9000)')
  parser.add_argument('-r', '--red_pin', type=int,
                      default=12,
                      help='number for red channel on GPIO board as numbered by board numbering, not BCM numbering (default: 12)')
  parser.add_argument('-g', '--green_pin', type=int,
                      default=13,
                      help='number for green channel on GPIO board as numbered by board numbering, not BCM numbering (default: 13)')
  parser.add_argument('-b', '--blue_pin', type=int,
                      default=16,
                      help='number for blue channel on GPIO board as numbered by board numbering, not BCM numbering (default: 16)')

  args = parser.parse_args()

  print 'WebSocket server at %s on port %d' % (args.address, args.port_number)
  print 'RGB channels at r: %d, g: %d, b: %d' % (args.red_pin, args.green_pin, args.blue_pin)

  return args


def main():
  # Have id that uniquely identifies Raspberry Pi as a client to the hub server.
  # Change this id for private use. The following code is publicly known and
  # therefore not at all secure.
  idForRPi = '5a2649734c55285b24777e427e'
  
  # Get arguments for WebSocket server address and portal number.
  # To change them from the default values, set them as flag options.
  args = getArguments()
  serverPortURL = '%s:%d' % (args.address, args.port_number)

  # Create connection to I2C Bus on the Raspberry Pi to read in sensor data.
  i2c_input = openI2CBus()

  # Create 3 GPIO PWM channel objects for displaying the sensor's color data.
  channelObject = setupPWM(args.red_pin, args.green_pin, args.blue_pin)

  # Create factory.
  factory = DataClientFactory(serverPortURL, debug = True)
  factory.protocol = DataClientProtocol
  websocket.connectWS(factory)

  # Create one more thread. There's a main thread already.
  thread = threading.Thread(target=readI2CData, args=(i2c_input, factory, channelObject, idForRPi))
  thread.daemon = True
  thread.start()

  # Start handling requests across websocket.
  reactor.run()

  # TODO: figure out how to stop PWM channels (pR.stop()) and do GPIO.cleanup() after websocket is closed.


if __name__ == '__main__':
  main()