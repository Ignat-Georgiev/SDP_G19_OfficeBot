#!/usr/bin/env python2


# Library for sending UDP commands to an EV3
# Commands include: motors
# Message headers:
#   RQT: RPI -> EV3 request sensor data
#   SNR: EV3 -> RPI send sensor data
#   CMD: RPI -> EV3 send motor command
# EV3 IP: 169.254.21.39
# RPI IP: 169.254.21.44

from tcpcom_py3 import TCPServer
import pygame  # needed for joystick commands
import sys
import time
import os


tcp_ip = "169.254.21.44"    # 169.254.21.44
tcp_port = 5005
tcp_reply = "Server message"
toSend = False
colorList = ("R", "W", "BW", "N", "BK", "BL", "G", "Y")
isConnected = False
reqSensorReceived = False
sensorData = None


def stateTrans(state, msg):
    global isConnected
    global reqSensorReceived
    global sensorData
    if state == "LISTENING":
        pass
        print("DEBUG: Server: Listening...")
    elif state == "CONNECTED":
        isConnected = True
        print("DEBUG: Server: Connected to ", msg)
    elif state == "MESSAGE":
        # print("DEBUG: Server: Message received: " + str(msg))
        if(msg[0:2] == "SNR"):
            reqSensorReceived = True
            sensorData = msg
            #print("DEBUG: Server: Sensor message received: ", str(sensorData))


def getSensors():
    server.sendMessage("RQT")
    while(not reqSensorReceived):
        pass
    return sensorData
# Sends a command mapped to a motor. Params:
# motor - either L or R, stands for left or right
# speed - int in range [-100, 100]


def sendMotorCommand(l_motor, r_motor, pause=False, stop=False):
    # Speed input error
    if(-100 <= int(l_motor) <= 100):
        pass
    else:
        raise Exception("ERROR: Wrong l_motor arg")
    # Speed input error
    if(-100 <= int(r_motor) <= 100):
        pass
    else:
        raise Exception("ERROR: Wrong r_motor arg")
    sendMsg = "CMD:" + str(l_motor) + "," + str(r_motor)
    server.sendMessage(sendMsg)
    # print("DEBUG: Server : Sending ", sendMsg)


def sendLineFollow(currentColor, nextColor, side, numJunctionsToIgnote):
    if(currentColor not in colorList):
        raise Exception("ERROR: Invalid currentColor input")
    if(nextColor not in colorList):
        raise Exception("ERROR: Invalid nextColor input")

    side = side.upper()[0]
    if(not (side == "L" or side == "R")):
        raise Exception("ERROR: Invalid side input")

    sendMsg = "LFW:" + currentColor + "," + nextColor + "," + side + "," + str(numJunctionsToIgnote)
    server.sendMessage(sendMsg)


# transform joystick inputs to motor outputs
def scale_stick(value):
    if value == 0.0:
        return 0.0
    else:
        return scale(value, (-1, 1), (-100, 100))


# Generic scale function
# Scale src range to dst range
def scale(val, src, dst):
    return (int(val - src[0]) / (src[1] - src[0])) * (dst[1] - dst[0]) + dst[0]


def attenuate(val, min, max):
    if val > max:
        return max
    if val < min:
        return min
    return val


def main():
    global server

    # Settings for the joystick
    yAxis = 5               # Joystick axis to read for up / down position
    xAxis = 0              # Joystick axis to read for left / right position
    # xPoll = False
    # yPoll = False
    xSpeed = 0
    ySpeed = 0

    print("Initialising TCP Server")
    server = TCPServer(5005, stateChanged=stateTrans)

    pygame.init()
    # Configuration for headless
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.display.init()
    screen = pygame.display.set_mode((1, 1))
    print("Waiting for joystick... (press CTRL+C to abort)")
    while True:
        try:
            try:
                pygame.joystick.init()
                # Attempt to setup the joystick
                if(pygame.joystick.get_count() < 1):
                    # No joystick attached, set LEDs blue
                    pygame.joystick.quit()
                    time.sleep(0.1)
                else:
                    # We have a joystick, attempt to initialise it!
                    joystick = pygame.joystick.Joystick(0)
                    break
            except pygame.error:
                # Failed to connect to the joystick
                pygame.joystick.quit()
                time.sleep(0.1)
        except KeyboardInterrupt:
            # CTRL+C exit, give up
            print("\nUser aborted")
            sys.exit()
    print("Joystick found")
    print("Initialising PS4 joystick")
    joystick.init()

    try:
        print("Press CTRL+C to quit")
        # Loop indefinitely
        while(True):
            # Get the latest events from the system
            hadEvent = False
            events = pygame.event.get()
            # Handle each event individually
            for event in events:
                if event.type == pygame.JOYBUTTONDOWN:
                    # A button on the joystick just got pushed down
                    hadEvent = True
                    print("DEBUG: had keypress event")
                elif event.type == pygame.JOYAXISMOTION:
                    # A joystick has been moved
                    # print("DEBUG: had joystick event")
                    # print(event.dict, event.joy, event.axis, event.value)
                    hadEvent = True
                    if event.axis == yAxis:
                        ySpeed = -joystick.get_axis(yAxis) * 100
                        # print("DEBUG: y axis used", str(ySpeed))
                    if event.axis == xAxis:
                        xSpeed = -joystick.get_axis(xAxis) * 100
                        # print("DEBUG: x axis used", str(xSpeed))

                if(hadEvent):
                    # Determine the drive power levels
                    # print("xspeed: " + str(xSpeed) + " yspeed: " + str(ySpeed))
                    l_wheel_speed = ySpeed - (xSpeed / 2)
                    r_wheel_speed = ySpeed + (xSpeed / 2)
                    l_wheel_speed = int(attenuate(l_wheel_speed, -100, 100))
                    r_wheel_speed = int(attenuate(r_wheel_speed, -100, 100))
                    # print("DEBUG: Joystick command send reached")

                    sendMotorCommand(l_wheel_speed, r_wheel_speed)

    except KeyboardInterrupt:
        # CTRL+C exit, disable all drives
        server.terminate()
        print("\nUser aborted")
        sys.exit()


if __name__ == '__main__':
    main()
