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
import logging
import math
import serial
import smbus
import sys
import threading
import time
from autobahn import websocket
from twisted.internet import reactor
from twisted.python import log


gamma_table = {}

arduino_lock = threading.Lock()
arduino = None


def populateGammaTable():
  for i in range(256):
    x = float(i)
    x /= 255
    x = math.pow(x, 2.5)
    x *= 255;
    
    gamma_table[i] = int(x)


class DataClientProtocol(websocket.WebSocketClientProtocol):
  """
  Simple client that connects to a WebSocket server, sends data, and prints everything it receives.
  """

  def onConnect(self, connectionResponse):
    logging.info('protocol onConnect')
    self.factory.register(self, connectionResponse)

  def onMessage(self, msg, binary):
    logging.info("Got message: " + msg)
    if not binary:
       # Validate that the message data is proper JSON dictionary with desired
       # keys.
       try:
         msg = validateData(msg)
       except ValueError, e:
         logging.warning(e)
         return
       
       if msg:
         sendDataToArduino(msg)


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
    logging.info("registered server " + response.peerstr)
    self.server = server

  def unregister(self, server):
    logging.info("unregistered server")
    self.server = None

  def clientConnectionFailed(self, connector, reason):
    logging.warning("connection failed: " + str(reason))
    time.sleep(1)
    logging.info("try reconnecting")
    connector.connect()

  def clientConnectionLost(self, connector, reason):
    logging.warning("connection lost: " + str(reason))

  def broadcast(self, msg):
    logging.info("broadcasting message: %s" % msg)
    if self.server is not None:
      self.server.sendMessage(msg)


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
    logging.warning("Device found\n")
    bus.write_byte(0x29, 0x80|0x00) # 0x00 = ENABLE register
    bus.write_byte(0x29, 0x01|0x02) # 0x01 = Power on, 0x02 RGB sensors enabled
    bus.write_byte(0x29, 0x80|0x0F) # 0x0F = control register for setting gain
    bus.write_byte(0x29, 0x01)      # 0x01 = 4x gain
    bus.write_byte(0x29, 0x80|0x01) # 0x01 = RGBC timing register
    bus.write_byte(0x29, 0xEB)      # 256 - 21 = 0xEB (21 * 2.4 ms = 50 ms)
    bus.write_byte(0x29, 0x80|0x14) # Reading results start register 14, LSB then MSB
    return bus
  else:
    logging.warning("Device not found\n")


# Read I2C data.
def readI2CData(i2c_input, factory, idString):
  while True:
    try:
      data = i2c_input.read_i2c_block_data(0x29, 0)
    except IOError:
      logging.warning("Could not read I2C data")
      continue

    clear = data[1] << 8 | data[0]
    red_raw = data[3] << 8 | data[2]
    green_raw = data[5] << 8 | data[4]
    blue_raw = data[7] << 8 | data[6]

    if clear is not 0:
      red_i = int((red_raw / float(clear)) * 255)
      green_i = int((green_raw / float(clear)) * 255)
      blue_i = int((blue_raw / float(clear)) * 255)
    else:
      red_i = 0
      green_i = 0
      blue_i = 0

    logging.info("%d, %d, %d, %d" % (red_raw, green_raw, blue_raw, clear))
    logging.info("%d, %d, %d" % (red_i, green_i, blue_i))

    try:
      red = gamma_table[red_i]
      green = gamma_table[green_i]
      blue = gamma_table[blue_i]
      #red = red_i
      #green = green_i
      #blue = blue_i
    except KeyError:
      continue
        
    logging.info("%d, %d, %d" % (red, green, blue))

    colors = {
      'red': red,
      'green': green,
      'blue': blue,
      'clear': int(clear),
      'id': idString
    }

    factory.broadcast(json.dumps(colors))
    #time.sleep(0.250)
    time.sleep(0.50)


def arduinoBackgroundConnector():
  global arduino
  while True:
    with arduino_lock:
      if arduino is None:
        try:
          arduino = serial.Serial('/dev/ttyACM0',
                                  baudrate=9600,
                                  bytesize=serial.EIGHTBITS,
                                  parity=serial.PARITY_NONE,
                                  stopbits=serial.STOPBITS_ONE,
                                  timeout=0,
                                  writeTimeout=0)
          time.sleep(2)
        except serial.SerialException:
          logging.warning('Arduino not available.')
    time.sleep(1)


# Validate data.
def validateData(data):
  # Check that data is in proper json format.
  try:
    obj = json.loads(data)
  except ValueError:
    raise ValueError, "Invalid json data: " + data

  # Check object is dictionary.
  if not isinstance(obj, dict):
    raise ValueError, "Object is not a dictionary, but type %s" % type(obj)

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


def sendDataToArduino(data):
  global arduino

  colors = {}
  for key, value in data.iteritems():
    if key != 'id':
      colors[key] = value
  expected_colors = ('red', 'green', 'blue')
  for color in expected_colors:
    if color not in colors:
      logging.warning('missing color %s, not updating color' % color)
      return

  logging.info('sending colors to Arduino: %s' % str(colors))
  message = ('\xFF\xFE' +
             chr(colors['red']) + chr(colors['green']) +
             chr(colors['blue']) +
             '\x00')

  with arduino_lock:
    if arduino is None:
      return

    try:
      arduino.read()
      written = arduino.write(message)
      if written < len(message):
        logging.warning('Wrote %d of %d bytes to Arduino.' %
                        (written, len(written)))
    except serial.SerialTimeoutException, e:
      logging.warning('Write timeout writing to Arduino.')
    except serial.SerialException, e:
      logging.warning('Error writing to Arduino: %s' % e)
      arduino = None


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

  logging.info('WebSocket server at %s on port %d' % (args.address, args.port_number))
  logging.info('RGB channels at r: %d, g: %d, b: %d' % (args.red_pin, args.green_pin, args.blue_pin))

  return args


def main():
  # Set up logging.
  _fmt = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
  logging.basicConfig(level=logging.DEBUG, format=_fmt)

  # Have id that uniquely identifies Raspberry Pi as a client to the hub server.
  # Change this id for private use. The following code is publicly known and
  # therefore not at all secure.
  idForRPi = '5a2649734c55285b24777e427e'

  populateGammaTable()

  # Get arguments for WebSocket server address and portal number.
  # To change them from the default values, set them as flag options.
  args = getArguments()
  serverPortURL = '%s:%d' % (args.address, args.port_number)

  # Create connection to I2C Bus on the Raspberry Pi to read in sensor data.
  i2c_input = openI2CBus()

  # Create factory.
  factory = DataClientFactory(serverPortURL, debug = True)
  factory.protocol = DataClientProtocol
  websocket.connectWS(factory)
  
  # Background thread to connect to the Arduino, and reconnect if it is
  # disconnected.
  arduino_thread = threading.Thread(target=arduinoBackgroundConnector)
  arduino_thread.daemon = True
  arduino_thread.start()

  # Create one more thread. There's a main thread already.
  thread = threading.Thread(target=readI2CData, args=(i2c_input, factory, idForRPi))
  thread.daemon = True
  thread.start()

  # Start handling requests across websocket.
  reactor.run()


if __name__ == '__main__':
  main()