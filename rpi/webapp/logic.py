#!/usr/bin/env python3

# multi-color lines detect in HSV and distance between middle of robot vision and center of line.
import sys
sys.path.append("../tcp/")
sys.path.append("../")

import numpy as np
import cv2
from tcp_rpi import *
import time
import datetime
import picamera
import picamera.array
from ir_reader import *
from psControl import *


desks = {
    1: {'name': 'Desk 1', 'color': 'orange'},
    2: {'name': 'Desk 2', 'color': 'green'},
    3: {'name': 'Desk 3', 'color': 'purple'},
    4: {'name': 'Desk 4', 'color': 'yellow'},
    5: {'name': 'Desk 5', 'color': 'red'},
    6: {'name': 'Desk 6', 'color': 'blue'}
}

directionsToTurnArray = [
    [("None", "None"), ("left", "left"), ("left", "right"), ("left", "right"), ("left", "left"), ("left", "right")],
    [("right", "right"), ("None", "None"), ("left", "right"), ("left", "right"), ("left", "left"), ("left", "right")],
    [("left", "right"), ("left", "right"), ("None", "None"), ("right", "right"), ("right", "left"), ("right", "right")],
    [("left", "right"), ("left", "right"), ("left", "left"), ("None", "None"), ("right", "left"), ("right", "right")],
    [("right", "right"), ("right", "right"), ("right", "left"), ("right", "left"), ("None", "None"), ("left", "right")],
    [("left", "right"), ("left", "right"), ("left", "left"), ("left", "left"), ("left", "right"), ("None", "None")]
]


def log_arrived_at(destination):
    log = open("log.txt", "a+")
    log.write("[" + datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S') + "] ")
    log.write("Successfully moved to " + str(destination) + ".\n")
    print("MOVED TO " + str(destination) + ". BACK TO PINGING FILE.")
    log.close()


# noinspection PyPep8Naming,PyRedundantParentheses
class line_detect():
    def __init__(self):
        self.width = 320
        self.height = 240
        self.numSlices = 4

        weight_1 = (0.9)
        weight_2 = (0.45, 0.45)
        weight_3 = (0.3, 0.3, 0.3)
        weight_4 = (0.23, 0.23, 0.23, 0.23)

        self.weights = (weight_1, weight_2, weight_3, weight_4)

        self.threshold = 20 * self.numSlices
        self.FPS_limit = 10

        self.previousSpeeds = (0, 0)

        self.slicesByColor = {
            "black": [],
            "blue": [],
            "red": [],
            "purple": [],
            "green": [],
            "yellow": [],
            "white": [],
            "pink" : [],
            "brown": [],
            "gray": [],
            "orange": [],
        }

        # initialising numpy upper and lower bounds for cv2 mask
        blackLower = self.transfer([0, 0, 0])
        blackUpper = self.transfer([0.278, 1, 0.294])

        yellowLower = self.transfer([0.02, 0.437, 0.283])
        yellowUpper = self.transfer([0.23,0.84, 0.867])

        blueLower = self.transfer([0.533, 0.709, 0.309])
        blueUpper = self.transfer([0.675, 1, 0.765])

        redLower = self.transfer([-0.067, 0.581, 0.304])
        redUpper = self.transfer([0.100, 0.941, 0.787])

        pinkLower = self.transfer([0.903, 0.736, 0.283])
        pinkUpper = self.transfer([1, 1, 0.739])

        greenLower = self.transfer([0.429, 0.853, 0.197])
        greenUpper = self.transfer([0.523, 1, 0.776])

        orangeLower = self.transfer([0.046, 0.757, 0.357])
        orangeUpper = self.transfer([0.102, 1, 1])

        purpleLower = self.transfer([0.766, 0.464, 0.240])
        purpleUpper = self.transfer([0.848, 0.749, 0.787])

        self.kernel = np.ones((5, 5), np.uint8)

        self.colorToMask = {
            "black": (blackLower, blackUpper),
            "blue": (blueLower, blueUpper),
            "yellow": (yellowLower, yellowUpper),
            "red": (redLower, redUpper),
            "green": (greenLower, greenUpper),
            "purple": (purpleLower, purpleUpper),
            "pink" : (pinkLower, pinkUpper),
            "orange": (orangeLower, orangeUpper),
        }


    def RemoveBackground_HSV(self, image, color):
        (lower, upper) = self.colorToMask[color]

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        mask = cv2.inRange(hsv, lower, upper)
        mask = cv2.dilate(mask, self.kernel, iterations=5)
        mask = cv2.erode(mask, self.kernel, iterations=4)

        image = cv2.bitwise_and(image, image, mask=mask)
        image = cv2.bitwise_not(image, image, mask=mask)
        image = (255 - image)

        return image

    def transfer(self, color_Range):
        color_Range[0] = int(color_Range[0]*180)
        color_Range[1] = int(color_Range[1]*255)
        color_Range[2] = int(color_Range[2]*255)
        return np.array([color_Range[0], color_Range[1], color_Range[2]])

    # Process the image and return the contour of line, it will change image to gray scale
    @staticmethod
    def getContours(img):
        element = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))

        imgray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  # Convert to Gray Scale

        # remove noise from image, such that only 15x15 pixel blocks exist
        dst = cv2.morphologyEx(imgray, cv2.MORPH_OPEN, element)

        # ignore any pixels with values greater than 100 (only want the darker pixels)
        _, threshold = cv2.threshold(dst, 100, 255, cv2.THRESH_BINARY_INV)

        _, contours, _ = cv2.findContours(threshold, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        return contours

    # get the center of contour
    @staticmethod
    def getContourCenter(contour):
        M = cv2.moments(contour)

        if M["m00"] == 0:
            return 0

        x = int(M["m10"] / M["m00"])
        y = int(M["m01"] / M["m00"])
        return (x, y)

    # return contours greater than requiredPercentageSize% of the image area
    @staticmethod
    def thresholdContourSize(img, height, width, requiredPercentageSize=20):
        totalImageArea = height * width
        contour = []
        for i in range(len(img)):
            cnt = img[i]
            area = cv2.contourArea(cnt)

            # if contour takes up 20% or more of the total area
            if (area >= totalImageArea * requiredPercentageSize/100):
                contour.append(cnt)

        return contour

    # it will concatenate the image in array
    @staticmethod
    def repackSlices(slices):
        image = slices[0]
        for i in range(len(slices)):
            if i != 0:
                image = np.concatenate((image, slices[i]), axis=0)
        return image

    # def draw(self, img, contour):
    #     if self.getContourCenter(contour) != 0:
    #         self.contourCenterX = self.getContourCenter(contour)[0]
    #     self.dir =  int((self.middleX-self.contourCenterX) * self.getContourExtent(contour))
    #     cv2.drawContours(img,contour,-1,(0,255,0),3) #Draw Contour GREEN
    #     cv2.circle(img, (self.contourCenterX, self.middleY), 7, (255,255,255), -1) #Draw dX circle WHITE
    #     cv2.circle(img, (self.middleX, self.middleY), 3, (0,0,255), -1) #Draw middle circle RED

    @staticmethod
    def getContourExtent(contour):
        area = cv2.contourArea(contour)
        _, _, w, h = cv2.boundingRect(contour)
        rect_area = w*h*3
        if rect_area > 0:
            return (float(area) / rect_area)

    # this is the main function which will return an array which contains all distance bias for every point
    def computeDistanceBiases(self, image, numberOfSlices, color):
        # divide the image horizontally into numberOfSlices
        # find contours of slice

        sliceHeight = int(self.height / numberOfSlices)
        distance = []

        # ignore the 20% of each side of the image
        widthOffset = int(self.width*0.1)

        for i in range(numberOfSlices):
            heightOffset = sliceHeight*i
            crop_img = image[heightOffset:heightOffset + sliceHeight, widthOffset:self.width-widthOffset]

#           self.slicesByColor[color].append(crop_img)

            height, width = crop_img.shape[:2]
            middleh = int(height/2)
            middlew = int(width/2)

            contours = self.getContours(crop_img)
            contours = self.thresholdContourSize(contours, height, width)

 #          cv2.drawContours(crop_img, contours, -1, (0, 255, 0), 3)
 #          cv2.circle(crop_img, (middlew, middleh), 7, (0, 0, 255), -1)  # Draw middle circle RED
            if contours:
                contourCenterX = self.getContourCenter(contours[0])[0]
#               cv2.circle(crop_img, (contourCenterX, middleh), 7, (255, 255, 255), -1)  # Draw dX circle WHITE
#               font = cv2.FONT_HERSHEY_SIMPLEX
#               cv2.putText(crop_img, str(middlew - contourCenterX), (contourCenterX + 20, middleh), font, 1, (200, 0, 200), 2, cv2.LINE_AA)

                bias = int(middlew - contourCenterX)
                distance.append(bias)

        # return distance array reversed
        return distance[::-1]

    def isColorInFrame(self, image):
        height, width = image.shape[:2]

        # get contours of image
        contours = self.getContours(image)

        # get contours larger than 5% of image area
        contours = self.thresholdContourSize(contours, height, width, 5)
        return len(contours) > 0

    # this function will detect whether there is a circle(destination) in the robot vision
    @staticmethod
    def circle_detect(img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # minDistBetweenCentres is high as we only need to detect one circle

        circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, 1, minDist=10000, param1=100, param2=20, minRadius=10, maxRadius=240)
        return (circles is not None)

    # through the distance bias array, we can use this function to reach line_following
    def computeWheelSpeeds(self, distanceBiasArray):
        if len(distanceBiasArray) > 0:
            bias = sum(distanceBiasArray)

            # bias = sum(distance)
            print('The distance list is {}'.format(distanceBiasArray))
            print('The bias is {}'.format(bias))

            # attenuate ensures speed will be between -40 and 40   -  parser requires speed to be an integer
            speed = int(attenuate(bias/12, -50, 50))

            if abs(bias) < self.threshold:
                return (50, 50)

            # robot is to the right of the line
            if bias > 0:
                self.previousSpeeds = (25 - speed, 25 + speed)
                return (25 - speed, 25 + speed)

            else:
                self.previousSpeeds = (25 - speed, 25 + speed)
                return (25 + abs(speed), 25 - abs(speed))

        # no main line is detected -> reverse
        else:
            (newRight, newLeft) = self.previousSpeeds
            return (-newLeft, -newRight)


def turn(direction):
    if direction == 'right':
        server.sendTurnCommand(100)

        # wait while turning
        time.sleep(2)

    elif direction == 'left':
        server.sendTurnCommand(-100)

        # wait while turning
        time.sleep(2)


def resetDictionary(d):
    for key in d:
        d[key] = []


# noinspection PyRedundantParentheses
# returns a list of turns
def compute_path(position, destination):
    # Debugging
    log = open("log.txt", "a+")
    log.write("[" + datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S') + "] ")
    log.write("Received command to move to " + str(destination) + ".\n")

    firstTurnColor = desks[position]['color']
    secondTurnColor = desks[destination]['color']

    (firstTurnDirection, secondTurnDirection) = directionsToTurnArray[position-1][destination-1]  # -1 because desks are 1 indexed, array is 0 indexed

    # Debugging
    debug_text = "COMPUTING ROUTE.\n" \
                 "Position: {} ({})\tDestination: {} ({})\n" \
                 "First Junction: {}\tSecond Junction: {}\n" \
                 "MOVING.".format(position, firstTurnColor, destination, secondTurnColor, firstTurnDirection, secondTurnDirection)
    print(debug_text)
    log.write("[" + datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S') + "] ")
    log.write(debug_text + "\n")
    log.close()

    return ((firstTurnColor, firstTurnDirection), (secondTurnColor, secondTurnDirection))


def main():
    global server, ESCAPE_KEY, camera, line, mainLineColor, resolution, ir_sensors, IR_THRESHOLD

    position = 1

    server = Server(5005)

    resolution = (320, 240)

    camera = picamera.PiCamera(resolution=resolution, framerate=60)

    # flip the image vertically and horizontally (because the camera is upside down)
    camera.vflip = True
    camera.hflip = True

    # required for the camera to 'warm up'
    time.sleep(0.1)

    line = line_detect()

    # set up ir sensors and threshold
    ir_sensors = IR_Bus()
    ir_sensors.setDaemon(True)
    ir_sensors.start()

    IR_THRESHOLD = 400

    mainLineColor = 'black'

    ESCAPE_KEY = 27
    MANUAL_OVERRIDE_START = 100
    MANUAL_OVERRIDE_CANCEL = 200

    while True:
        destination = getDestinationFromFile()
        if destination is not None and destination is not MANUAL_OVERRIDE_CANCEL:
            clearFile()
            if destination == position:
                print("Destination is the same as current position. Skipping.")

            elif destination == MANUAL_OVERRIDE_START:
                handleManualOverride()

            else:
                if destination not in [1, 2, 3, 4, 5, 6]:
                    print("Destination not valid!")
                else:
                    path = compute_path(position, destination)

                    # follow the computed path, return when completed or escaped
                    try:
                        server.sendSpeakCommand("Heading to desk " + str(destination))
                        followPath(path)

                        log_arrived_at(destination)
                        server.sendSpeakCommand("Arrived at desk " + str(destination))
                        position = destination

                        # wait 5 secs while at destination
                        time.sleep(5)

                    except KeyboardInterrupt:
                        # Escape key was pressed
                        server.sendMotorCommand(0, 0)
                        camera.close()
                        cv2.destroyAllWindows()
                        break

        else:
            print("File was empty.")
            time.sleep(1)

def writeManualExitToFile():
    file = open("dest.txt", "r+")
    # empty the file just in case
    file.seek(0)
    file.truncate()
    file.write("200")
    file.close()
    print("Writing 200 to file.")

def handleManualOverride():
    server.sendSpeakCommand("Manual override enabled.")
    print("MANUAL OVERRIDE ENABLED.")
    joy = psControl()

    while True:
        joy_val = joy.spin()
        if joy_val is False:
            break
        elif joy_val is not True:
            server.sendMotorCommand(joy_val[0], joy_val[1])
    server.sendMotorCommand(0, 0)
    writeManualExitToFile()
    server.sendSpeakCommand("Manual override disabled.")
    print("MANUAL OVERRIDE DISABLED.")


# checks if there is a new destination to go to (written by app.py)
def getDestinationAndClearFile():
    destination = getDestinationFromFile()
    if destination is not None:
        clearFile()
    return destination


def clearFile():
    file = open("dest.txt", "r+")
    file.seek(0)
    file.truncate()
    file.close()


def getDestinationFromFile():
    file = open("dest.txt", "r+")
    content = file.read()
    if len(content) > 0:
        print("File content: " + content)
        destination = int(content)
        return destination
    else:
        return None

# follows the given path until a circle marking the end of path is detected
def followPath(path):
    for junction in path:
        followTillJunction(junction)
    followTillEnd()


def followTillJunction(junction):
    (junctionColor, turnDirection) = junction

    rawCapture = picamera.array.PiRGBArray(camera, size=resolution)
    startTime = time.time()

    previousSpeeds = (0,0)
    # Capture images, opencv uses bgr format, using video port is faster but takes lower quality images
    for _ in camera.capture_continuous(rawCapture, format='bgr', use_video_port=True):

        rawCapture.truncate(0)  # clear the rawCapture array

        frame = rawCapture.array

        # reset the arrays of slices
        line.slicesByColor[mainLineColor] = []
        line.slicesByColor[junctionColor] = []

        # isolating colors and getting distance between centre of vision and centre of line
        frameWithoutBackground = line.RemoveBackground_HSV(frame, mainLineColor)
        mainLineDistanceBiases = line.computeDistanceBiases(frameWithoutBackground, line.numSlices, mainLineColor)

        HSV_turnColor = line.RemoveBackground_HSV(frame, junctionColor)
        isTurnColorInFrame = line.isColorInFrame(HSV_turnColor)

        if isTurnColorInFrame:
            print("Turning " + turnDirection)
            turn(turnDirection)
            return
        else:
            (new_left_motor_speed, new_right_motor_speed) = line.computeWheelSpeeds(mainLineDistanceBiases)

            if (new_left_motor_speed, new_right_motor_speed) != previousSpeeds:
                server.sendMotorCommand(new_left_motor_speed, new_right_motor_speed)
                print('DEBUG: left motor speed: {}'.format(new_left_motor_speed))
                print('DEBUG: right motor speed: {}'.format(new_right_motor_speed))
                previousSpeeds = (new_left_motor_speed, new_right_motor_speed)


#            printLinesToScreen(mainLineColor, junctionColor)

        print(time.time() - startTime)
        startTime = time.time()

        if isIRSensorValueClose():
            server.sendMotorCommand(0,0)
            previousSpeeds = (0, 0)

            server.sendSpeakCommand("MOVE OUT THE WAY")
            print("Sensor detected something")

            while isIRSensorValueClose():
                pass
            print("Something is no longer in the way")

def followTillEnd():

    rawCapture = picamera.array.PiRGBArray(camera, size=resolution)
    startTime = time.time()

    previousSpeeds = (0, 0)

    # Capture images, opencv uses bgr format, using video port is faster but takes lower quality images
    for _ in camera.capture_continuous(rawCapture, format='bgr', use_video_port=True):
        rawCapture.truncate(0)  # clear the rawCapture array

        frame = rawCapture.array

        # reset the array of slices
        line.slicesByColor[mainLineColor] = []

        # isolating colors and getting distance between centre of vision and centre of line
        frameWithoutBackground = line.RemoveBackground_HSV(frame, mainLineColor)
        mainLineDistanceBiases = line.computeDistanceBiases(frameWithoutBackground, line.numSlices, mainLineColor)

        isCircleInFrame = line.circle_detect(frame)

        if isCircleInFrame:
            # arrived at destination, turn around, stop motors and return
            server.sendTurnCommand(180)

            # wait while turning
            time.sleep(4)

            server.sendMotorCommand(0, 0)
            return
        else:
            (new_left_motor_speed, new_right_motor_speed) = line.computeWheelSpeeds(mainLineDistanceBiases)

            if (new_left_motor_speed, new_right_motor_speed) != previousSpeeds:
                server.sendMotorCommand(new_left_motor_speed, new_right_motor_speed)
                print('DEBUG: left motor speed: {}'.format(new_left_motor_speed))
                print('DEBUG: right motor speed: {}'.format(new_right_motor_speed))
                previousSpeeds = (new_left_motor_speed, new_right_motor_speed)

        print(time.time() - startTime)
        startTime = time.time()

#        printLinesToScreen(mainLineColor)

        if isIRSensorValueClose():
            server.sendMotorCommand(0,0)
            previousSpeeds = (0, 0)

            server.sendSpeakCommand("MOVE OUT THE WAY")
            print("Sensor detected something")

            while isIRSensorValueClose():
                pass
            print("Something is no longer in the way")


def printLinesToScreen(*listOfColors):
    for color in listOfColors:
        slices = line.slicesByColor[color]

        # join slices back together
        image = line.repackSlices(slices)

        # output image to screen
        cv2.imshow(color, image)

    # required when printing lines to the screen
    pressedKey = cv2.waitKey(1) & 0xff
    if pressedKey == ESCAPE_KEY:
        raise KeyboardInterrupt('Exit key was pressed')

def isIRSensorValueClose():
    if int(float(ir_sensors.IR_LR)) > IR_THRESHOLD:
        return True

    if int(float(ir_sensors.IR_RR)) > IR_THRESHOLD:
        return True

    if int(float(ir_sensors.IR_LF)) > IR_THRESHOLD:
        return True

    if int(float(ir_sensors.IR_RF)) > IR_THRESHOLD:
        return True

    return False

if __name__ == '__main__':
    main()
