#!/usr/bin/env python3
import argparse
import json
from pydoc import render_doc
import shutil
import traceback
from argparse import ArgumentParser
from pathlib import Path
import time
from datetime import datetime, timedelta
from collections import deque 

import cv2
from cv2 import resize
import depthai as dai
import numpy as np
import copy

import depthai_helpers.calibration_utils as calibUtils

font = cv2.FONT_HERSHEY_SIMPLEX
debug = False
red = (255, 0, 0)
green = (0, 255, 0)

stringToCam = {
                # 'RGB': dai.CameraBoardSocket.RGB,
                # 'LEFT': dai.CameraBoardSocket.LEFT,
                # 'RIGHT': dai.CameraBoardSocket.RIGHT,
                # 'AUTO': dai.CameraBoardSocket.AUTO,
                # 'CAM_A' : dai.CameraBoardSocket.RGB,
                # 'CAM_B' : dai.CameraBoardSocket.LEFT,
                # 'CAM_C' : dai.CameraBoardSocket.CAM_C,
                'RGB'   : dai.CameraBoardSocket.CAM_A,
                'LEFT'  : dai.CameraBoardSocket.CAM_B,
                'RIGHT' : dai.CameraBoardSocket.CAM_C,
                'CAM_A' : dai.CameraBoardSocket.CAM_A,
                'CAM_B' : dai.CameraBoardSocket.CAM_B,
                'CAM_C' : dai.CameraBoardSocket.CAM_C,
                'CAM_D' : dai.CameraBoardSocket.CAM_D,
                'CAM_E' : dai.CameraBoardSocket.CAM_E,
                'CAM_F' : dai.CameraBoardSocket.CAM_F,
                'CAM_G' : dai.CameraBoardSocket.CAM_G,
                'CAM_H' : dai.CameraBoardSocket.CAM_H
                }

CamToString = {
                # dai.CameraBoardSocket.RGB : 'RGB'  ,
                # dai.CameraBoardSocket.LEFT : 'LEFT' ,
                # dai.CameraBoardSocket.RIGHT : 'RIGHT',
                # dai.CameraBoardSocket.AUTO : 'AUTO'
                dai.CameraBoardSocket.CAM_A : 'RGB'  ,
                dai.CameraBoardSocket.CAM_B : 'LEFT' ,
                dai.CameraBoardSocket.CAM_C : 'RIGHT',
                dai.CameraBoardSocket.CAM_A : 'CAM_A',
                dai.CameraBoardSocket.CAM_B : 'CAM_B',
                dai.CameraBoardSocket.CAM_C : 'CAM_C',
                dai.CameraBoardSocket.CAM_D : 'CAM_D',
                dai.CameraBoardSocket.CAM_E : 'CAM_E',
                dai.CameraBoardSocket.CAM_F : 'CAM_F',
                dai.CameraBoardSocket.CAM_G : 'CAM_G',
                dai.CameraBoardSocket.CAM_H : 'CAM_H'
                }

camToMonoRes = {
                'OV7251' : dai.MonoCameraProperties.SensorResolution.THE_480_P,
                'OV9*82' : dai.MonoCameraProperties.SensorResolution.THE_800_P,
                }

camToRgbRes = {
                'IMX378' : dai.ColorCameraProperties.SensorResolution.THE_4_K,
                'IMX214' : dai.ColorCameraProperties.SensorResolution.THE_4_K,
                'OV9*82' : dai.ColorCameraProperties.SensorResolution.THE_800_P,
                'IMX582' : dai.ColorCameraProperties.SensorResolution.THE_12_MP,
                'AR0234' : dai.ColorCameraProperties.SensorResolution.THE_1200_P
                }

def create_blank(width, height, rgb_color=(0, 0, 0)):
    """Create new image(numpy array) filled with certain color in RGB"""
    # Create black blank image
    image = np.zeros((height, width, 3), np.uint8)

    # Since OpenCV uses BGR, convert the color first
    color = tuple(reversed(rgb_color))
    # Fill image with color
    image[:] = color

    return image


def parse_args():
    epilog_text = '''
    Captures and processes images for disparity depth calibration, generating a `<device id>.json` file or `depthai_calib.json`
    that should be loaded when initializing depthai. By default, captures one image for each of the 8 calibration target poses.

    Image capture requires the use of a printed OpenCV charuco calibration target applied to a flat surface(ex: sturdy cardboard).
    Default board size used in this script is 22x16. However you can send a customized one too.
    When taking photos, ensure enough amount of markers are visible and images are crisp. 
    The board does not need to fit within each drawn red polygon shape, but it should mimic the display of the polygon.

    If the calibration checkerboard corners cannot be found, the user will be prompted to try that calibration pose again.

    The script requires a RMS error < 1.0 to generate a calibration file. If RMS exceeds this threshold, an error is displayed.
    An average epipolar error of <1.5 is considered to be good, but not required. 

    Example usage:

    Run calibration with a checkerboard square size of 3.0cm and marker size of 2.5cm  on board config file DM2CAM:
    python3 calibrate.py -s 3.0 -ms 2.5 -brd DM2CAM

    Only run image processing only with same board setup. Requires a set of saved capture images:
    python3 calibrate.py -s 3.0 -ms 2.5 -brd DM2CAM -m process
    
    Delete all existing images before starting image capture:
    python3 calibrate.py -i delete
    '''
    parser = ArgumentParser(
        epilog=epilog_text, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-c", "--count", default=1, type=int, required=False,
                        help="Number of images per polygon to capture. Default: 1.")
    parser.add_argument("-s", "--squareSizeCm", type=float, required=True,
                        help="Square size of calibration pattern used in centimeters. Default: 2.0cm.")
    parser.add_argument("-ms", "--markerSizeCm", type=float, required=False,
                        help="Marker size in charuco boards.")
    parser.add_argument("-db", "--defaultBoard", default=False, action="store_true",
                        help="Calculates the -ms parameter automatically based on aspect ratio of charuco board in the repository")
    parser.add_argument("-nx", "--squaresX", default="11", type=int, required=False,
                        help="number of chessboard squares in X direction in charuco boards.")
    parser.add_argument("-ny", "--squaresY", default="8", type=int, required=False,
                        help="number of chessboard squares in Y direction in charuco boards.")
    parser.add_argument("-rd", "--rectifiedDisp", default=True, action="store_false",
                        help="Display rectified images with lines drawn for epipolar check")
    parser.add_argument("-drgb", "--disableRgb", default=False, action="store_true",
                        help="Disable rgb camera Calibration")
    parser.add_argument("-slr", "--swapLR", default=False, action="store_true",
                        help="Interchange Left and right camera port.")
    parser.add_argument("-m", "--mode", default=['capture', 'process'], nargs='*', type=str, required=False,
                        help="Space-separated list of calibration options to run. By default, executes the full 'capture process' pipeline. To execute a single step, enter just that step (ex: 'process').")
    parser.add_argument("-brd", "--board", default=None, type=str, required=True,
                        help="BW1097, BW1098OBC - Board type from resources/boards/ (not case-sensitive). "
                        "Or path to a custom .json board config. Mutually exclusive with [-fv -b -w]")
    parser.add_argument("-iv", "--invertVertical", dest="invert_v", default=False, action="store_true",
                        help="Invert vertical axis of the camera for the display")
    parser.add_argument("-ih", "--invertHorizontal", dest="invert_h", default=False, action="store_true",
                        help="Invert horizontal axis of the camera for the display")
    # parser.add_argument("-ep", "--maxEpiploarError", default="1.0", type=float, required=False,
    #                     help="Sets the maximum epiploar allowed with rectification")
    parser.add_argument("-cm", "--cameraMode", default="perspective", type=str,
                        required=False, help="Choose between perspective and Fisheye")
    parser.add_argument("-rlp", "--rgbLensPosition", default=135, type=int,
                        required=False, help="Set the manual lens position of the camera for calibration")
    parser.add_argument("-fps", "--fps", default=10, type=int,
                        required=False, help="Set capture FPS for all cameras. Default: %(default)s")
    parser.add_argument("-cd", "--captureDelay", default=5, type=int,
                        required=False, help="Choose how much delay to add between pressing the key and capturing the image. Default: %(default)s")
    parser.add_argument("-d", "--debug", default=False, action="store_true", help="Enable debug logs.")
    parser.add_argument("-fac", "--factoryCalibration", default=False, action="store_true",
                        help="Enable writing to Factory Calibration.")
    parser.add_argument("-osf", "--outputScaleFactor", type=float, default=0.5,
                        help="set the scaling factor for output visualization. Default: 0.5.")

    options = parser.parse_args()

    # Set some extra defaults, `-brd` would override them
    if options.markerSizeCm is None:
        if options.defaultBoard:
            options.markerSizeCm = options.squareSizeCm * 0.75
        else:
            raise argparse.ArgumentError(options.markerSizeCm, "-ms / --markerSizeCm needs to be provided (you can use -db / --defaultBoard if using calibration board from this repository or calib.io to calculate -ms automatically)")
    if options.squareSizeCm < 2.2:
        raise argparse.ArgumentTypeError("-s / --squareSizeCm needs to be greater than 2.2 cm")
        
    return options

class HostSync:
    def __init__(self, deltaMilliSec):
        self.arrays = {}
        self.arraySize = 15
        self.recentFrameTs = None
        self.deltaMilliSec = timedelta(milliseconds=deltaMilliSec)
        # self.synced = queue.Queue()

    def remove(self, t1):
            return timedelta(milliseconds=500) < (self.recentFrameTs - t1)

    def add_msg(self, name, data, ts):
        if name not in self.arrays:
            self.arrays[name] = deque(maxlen=self.arraySize)
        # Add msg to array
        self.arrays[name].appendleft({'data': data, 'timestamp': ts})
        if self.recentFrameTs == None or self.recentFrameTs - ts:
            self.recentFrameTs = ts
        # print(len(self.arrays[name]))
        # print(f'Added Msgs typ {name}')
        # print(ts)
        # for name, arr in self.arrays.items():
        #     for i, obj in enumerate(arr):
        #         if self.remove(obj['timestamp']):
        #             arr.remove(obj)
        #         else: break
    
    def clearQueues(self):
        print('Clearing Queues...')
        for name, msgList in self.arrays.items():
            self.arrays[name].clear()
            print(len(self.arrays[name]))

    def get_synced(self):
        synced = {}
        for name, msgList in self.arrays.items():
            # print('len(pivotM---------sgList)')
            # print(len(pivotMsgList))

            if len(msgList) != self.arraySize:
                return False 

        for name, pivotMsgList in self.arrays.items():
            print('len(pivotMsgList)')
            print(len(pivotMsgList))
            pivotMsgListDuplicate = pivotMsgList
            while pivotMsgListDuplicate:
                currPivot = pivotMsgListDuplicate.popleft()
                synced[name] = currPivot['data']
                
                for subName, msgList in self.arrays.items():
                    print(f'len of {subName}')
                    print(len(msgList))
                    if name == subName:
                        continue
                    msgListDuplicate = msgList.copy()
                    while msgListDuplicate:
                        print(f'---len of dup {subName} is {len(msgListDuplicate)}')
                        currMsg = msgListDuplicate.popleft()
                        time_diff = abs(currMsg['timestamp'] - currPivot['timestamp'])
                        print(f'---Time diff is {time_diff} and delta is {self.deltaMilliSec}')
                        if time_diff < self.deltaMilliSec:
                            print(f'--------Adding {subName} to sync. Messages left is {len(msgListDuplicate)}')
                            synced[subName] = currMsg['data']
                            break
                    print(f'Size of Synced is {len(synced)} amd array size is {len(self.arrays)}')
                    if len(synced) == len(self.arrays):
                        self.clearQueues()
                        return synced

            # raise SystemExit(1)
            self.clearQueues()
            return False


        """ for name, arr in self.arrays.items():
            for i, obj in enumerate(arr):
                time_diff = abs(obj['timestamp'] - self.recentFrameTs)
                print("Time diff for {0} is {1} milliseconds".format(name ,time_diff.total_seconds() * 1000))
                # 20ms since we add rgb/depth frames at 30FPS => 33ms. If
                # time difference is below 20ms, it's considered as synced
                if time_diff < self.deltaMilliSec:
                    synced[name] = obj['data']
                    # print(f"{name}: {i}/{len(arr)}")
                    break
        print(f'Size of Synced is {len(synced)} amd array size is {len(self.arrays)}')
        if len(synced) == len(self.arrays):
            for name, arr in self.arrays.items():
                for i, obj in enumerate(arr):
                    if self.remove(obj['timestamp']):
                        arr.remove(obj)
                    else: break
            return synced
        return False """

class Main:
    output_scale_factor = 0.5
    polygons = None
    width = None
    height = None
    current_polygon = 0
    images_captured_polygon = 0
    images_captured = 0

    def __init__(self):
        global debug
        self.args = parse_args()
        debug = self.args.debug
        self.output_scale_factor = self.args.outputScaleFactor
        self.aruco_dictionary = cv2.aruco.Dictionary_get(
            cv2.aruco.DICT_4X4_1000)
        self.focus_value = self.args.rgbLensPosition
        if self.args.board:
            board_path = Path(self.args.board)
            if not board_path.exists():
                board_path = (Path(__file__).parent / 'resources/boards' / self.args.board.upper()).with_suffix('.json').resolve()
                if not board_path.exists():
                    raise ValueError(
                        'Board config not found: {}'.format(board_path))
            with open(board_path) as fp:
                self.board_config = json.load(fp)
                self.board_config = self.board_config['board_config']
                self.board_config_backup = self.board_config

        # TODO: set the total images
        # random polygons for count
        self.total_images = self.args.count * \
            len(calibUtils.setPolygonCoordinates(1000, 600))
        if debug:
            print("Using Arguments=", self.args)

        # if self.args.board.upper() == 'OAK-D-LITE':
        #     raise Exception(
        #     "OAK-D-Lite Calibration is not supported on main yet. Please use `lite_calibration` branch to calibrate your OAK-D-Lite!!")
        
        self.device = dai.Device()
        cameraProperties = self.device.getConnectedCameraProperties()
        for properties in cameraProperties:
            for in_cam in self.board_config['cameras'].keys():
                cam_info = self.board_config['cameras'][in_cam]
                if properties.socket == stringToCam[in_cam]:
                    self.board_config['cameras'][in_cam]['sensorName'] = properties.sensorName
                    print('Cam: {} and focus: {}'.format(cam_info['name'], properties.hasAutofocus))
                    self.board_config['cameras'][in_cam]['hasAutofocus'] = properties.hasAutofocus
                    # self.auto_checkbox_dict[cam_info['name']  + '-Camera-connected'].check()
                    break

        pipeline = self.create_pipeline()
        self.device.startPipeline(pipeline)

        self.camera_queue = {}
        for config_cam in self.board_config['cameras']:
            cam = self.board_config['cameras'][config_cam]
            self.camera_queue[cam['name']] = self.device.getOutputQueue(cam['name'], 1, False)

        """ cameraProperties = self.device.getConnectedCameraProperties()
        for properties in cameraProperties:
            if properties.sensorName == 'OV7251':
                raise Exception(
            "OAK-D-Lite Calibration is not supported on main yet. Please use `lite_calibration` branch to calibrate your OAK-D-Lite!!") 

        self.device.startPipeline(pipeline)"""
        # self.left_camera_queue = self.device.getOutputQueue("left", 30, True)
        # self.right_camera_queue = self.device.getOutputQueue("right", 30, True)
        # if not self.args.disableRgb:
        #     self.rgb_camera_queue = self.device.getOutputQueue("rgb", 30, True)

    def is_markers_found(self, frame):
        marker_corners, _, _ = cv2.aruco.detectMarkers(
            frame, self.aruco_dictionary)
        print("Markers count ... {}".format(len(marker_corners)))
        return not (len(marker_corners) < self.args.squaresX*self.args.squaresY / 4)

    def test_camera_orientation(self, frame_l, frame_r):
        marker_corners_l, id_l, _ = cv2.aruco.detectMarkers(
            frame_l, self.aruco_dictionary)
        marker_corners_r, id_r, _ = cv2.aruco.detectMarkers(
            frame_r, self.aruco_dictionary)

        for i, left_id in enumerate(id_l):
            idx = np.where(id_r == left_id)
            # print(idx)
            if idx[0].size == 0:
                continue
            for left_corner, right_corner in zip(marker_corners_l[i], marker_corners_r[idx[0][0]]):
                if left_corner[0][0] - right_corner[0][0] < 0:
                    return False
        return True
    
    def create_pipeline(self):
        pipeline = dai.Pipeline()

        fps = 10
        for cam_id in self.board_config['cameras']:
            cam_info = self.board_config['cameras'][cam_id]
            if cam_info['type'] == 'mono':
                cam_node = pipeline.createMonoCamera()
                xout = pipeline.createXLinkOut()

                cam_node.setBoardSocket(stringToCam[cam_id])
                cam_node.setResolution(camToMonoRes[cam_info['sensorName']])
                cam_node.setFps(fps)

                xout.setStreamName(cam_info['name'])
                cam_node.out.link(xout.input)
            else:
                cam_node = pipeline.createColorCamera()
                xout = pipeline.createXLinkOut()
                
                cam_node.setBoardSocket(stringToCam[cam_id])
                cam_node.setResolution(camToRgbRes[cam_info['sensorName']])
                cam_node.setFps(fps)

                xout.setStreamName(cam_info['name'])
                cam_node.isp.link(xout.input)
                if cam_info['sensorName'] == "OV9*82":
                    cam_node.initialControl.setSharpness(0)
                    cam_node.initialControl.setLumaDenoise(0)
                    cam_node.initialControl.setChromaDenoise(4)

                if cam_info['hasAutofocus']:
                    cam_node.initialControl.setManualFocus(self.focus_value)

                    controlIn = pipeline.createXLinkIn()
                    controlIn.setStreamName(cam_info['name'] + '-control')
                    controlIn.out.link(cam_node.inputControl)
            xout.input.setBlocking(False)
            xout.input.setQueueSize(1)

        return pipeline


    def parse_frame(self, frame, stream_name):
        if not self.is_markers_found(frame):
            return False

        filename = calibUtils.image_filename(
            stream_name, self.current_polygon, self.images_captured)
        cv2.imwrite("dataset/{}/{}".format(stream_name, filename), frame)
        print("py: Saved image as: " + str(filename))
        return True

    def show_info_frame(self):
        info_frame = np.zeros((600, 1000, 3), np.uint8)
        print("Starting image capture. Press the [ESC] key to abort.")
        print("Will take {} total images, {} per each polygon.".format(
            self.total_images, self.args.count))

        def show(position, text):
            cv2.putText(info_frame, text, position,
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0))

        show((25, 100), "Information about image capture:")
        show((25, 160), "Press the [ESC] key to abort.")
        show((25, 220), "Press the [spacebar] key to capture the image.")
        show((25, 300), "Polygon on the image represents the desired chessboard")
        show((25, 340), "position, that will provide best calibration score.")
        show((25, 400), "Will take {} total images, {} per each polygon.".format(
            self.total_images, self.args.count))
        show((25, 550), "To continue, press [spacebar]...")

        cv2.imshow("info", info_frame)
        while True:
            key = cv2.waitKey(1)
            if key == ord(" "):
                cv2.destroyAllWindows()
                return
            elif key == 27 or key == ord("q"):  # 27 - ESC
                cv2.destroyAllWindows()
                raise SystemExit(0)

    def show_failed_capture_frame(self):
        width, height = int(
            self.width * self.output_scale_factor), int(self.height * self.output_scale_factor)
        info_frame = np.zeros((self.height, self.width, 3), np.uint8)
        print("py: Capture failed, unable to find chessboard! Fix position and press spacebar again")

        def show(position, text):
            cv2.putText(info_frame, text, position,
                        cv2.FONT_HERSHEY_TRIPLEX, 0.7, (0, 255, 0))

        show((50, int(height / 2 - 40)),
             "Capture failed, unable to find chessboard!")
        show((60, int(height / 2 + 40)), "Fix position and press spacebar again")

        # cv2.imshow("left", info_frame)
        # cv2.imshow("right", info_frame)
        cv2.imshow(self.display_name, info_frame)
        cv2.waitKey(2000)

    def show_failed_orientation(self):
        width, height = int(
            self.width * self.output_scale_factor), int(self.height * self.output_scale_factor)
        info_frame = np.zeros((height, width, 3), np.uint8)
        print("py: Capture failed, Swap the camera's ")

        def show(position, text):
            cv2.putText(info_frame, text, position,
                        cv2.FONT_HERSHEY_TRIPLEX, 0.7, (0, 255, 0))

        show((60, int(height / 2 - 40)), "Calibration failed, ")
        show((60, int(height / 2)), "Device might be held upside down!")
        show((60, int(height / 2)), "Or ports connected might be inverted!")
        show((60, int(height / 2 + 40)), "Fix orientation")
        show((60, int(height / 2 + 80)), "and start again")

        # cv2.imshow("left", info_frame)
        # cv2.imshow("right", info_frame)
        cv2.imshow("left + right", info_frame)
        cv2.waitKey(0)
        raise Exception(
            "Calibration failed, Camera Might be held upside down. start again!!")


    def empty_calibration(self, calib: dai.CalibrationHandler):
        data = calib.getEepromData()
        for attr in ["boardName", "boardRev"]:
            if getattr(data, attr): return False
        return True
    
    def capture_images_sync(self):
        finished = False
        capturing = False
        start_timer = False
        timer = self.args.captureDelay
        prev_time = None
        curr_time = None

        self.display_name = "Image Window"
        syncCollector = HostSync(60)
        while not finished:
            currImageList = {}
            for key in self.camera_queue.keys():
                frameMsg = self.camera_queue[key].get()

                # print(f'Timestamp of  {key} is {frameMsg.getTimestamp()}')

                syncCollector.add_msg(key, frameMsg, frameMsg.getTimestamp())
                gray_frame = None
                if frameMsg.getType() == dai.RawImgFrame.Type.RAW8:
                    gray_frame = frameMsg.getCvFrame()
                else:
                    gray_frame = cv2.cvtColor(frameMsg.getCvFrame(), cv2.COLOR_BGR2GRAY)
                currImageList[key] = gray_frame
                # print(gray_frame.shape)

            resizeHeight = 0
            resizeWidth = 0
            for name, imgFrame in currImageList.items():
                
                # print(f'original Shape of {name} is {imgFrame.shape}' )
                currImageList[name] = cv2.resize(
                    imgFrame, (0, 0), fx=self.output_scale_factor, fy=self.output_scale_factor)
                
                height, width = currImageList[name].shape

                widthRatio = resizeWidth / width
                heightRatio = resizeHeight / height


                # if widthRatio > 1.0 and heightRatio > 1.0 and widthRatio < 1.2 and heightRatio < 1.2:
                #     continue
                

                if (widthRatio > 0.8 and heightRatio > 0.8 and widthRatio <= 1.0 and heightRatio <= 1.0) or (widthRatio > 1.2 and heightRatio > 1.2) or (resizeHeight == 0):
                    resizeWidth = width
                    resizeHeight = height
                # elif widthRatio > 1.2 and heightRatio > 1.2:


                # if width < resizeWidth:
                #     resizeWidth = width
                # if height > resizeHeight:
                #     resizeHeight = height
            
            # print(f'Scale Shape  is {resizeWidth}x{resizeHeight}' )
            
            combinedImage = None
            for name, imgFrame in currImageList.items():
                height, width = imgFrame.shape
                if width > resizeWidth and height > resizeHeight:
                    imgFrame = cv2.resize(
                    imgFrame, (0, 0), fx= resizeWidth / width, fy= resizeWidth / width)
                
                # print(f'final_scaledImageSize is {imgFrame.shape}')
                if self.polygons is None:
                    self.height, self.width = imgFrame.shape
                    print(self.height, self.width)
                    self.polygons = calibUtils.setPolygonCoordinates(
                        self.height, self.width)
                
                cv2.polylines(
                    imgFrame, np.array([self.polygons[self.current_polygon]]),
                    True, (0, 0, 255), 4)
                
                # TODO(Sachin): Add this back with proper alignment
                # cv2.putText(
                #     imgFrame,
                #     "Polygon Position: {}. Captured {} of {} {} images".format(
                #         self.current_polygon + 1, self.images_captured, self.total_images, name),
                #     (0, 700), cv2.FONT_HERSHEY_TRIPLEX, 1.0, (255, 0, 0))

                height, width = imgFrame.shape
                height_offset = (resizeHeight - height)//2
                width_offset = (resizeWidth - width)//2
                subImage = np.pad(imgFrame, ((height_offset, height_offset), (width_offset,width_offset)), 'constant', constant_values=0)
                if combinedImage is None:
                    combinedImage = subImage
                else:
                    combinedImage = np.hstack((combinedImage, subImage))
            
            key = cv2.waitKey(1)
            if key == 27 or key == ord("q"):
                print("py: Calibration has been interrupted!")
                raise SystemExit(0)
            elif key == ord(" "):
                start_timer = True
                prev_time = time.time()
                timer = self.args.captureDelay

            if start_timer == True:
                curr_time = time.time()
                if curr_time - prev_time >= 1:
                    prev_time = curr_time
                    timer = timer - 1
                if timer <= 0 and start_timer == True:
                    start_timer = False
                    capturing = True
                    print('Start capturing...')
                
                image_shape = combinedImage.shape
                cv2.putText(combinedImage, str(timer),
                        (image_shape[1]//2, image_shape[0]//2), font,
                        7, (0, 255, 255),
                        4, cv2.LINE_AA)

            cv2.imshow(self.display_name, combinedImage)
            tried = {}
            allPassed = True

            if capturing:
                syncedMsgs = syncCollector.get_synced()
                if syncedMsgs == False:
                    for key in self.camera_queue.keys():
                        self.camera_queue[key].getAll()
                    continue 
                for name, frameMsg in syncedMsgs.items():
                    tried[name] = self.parse_frame(frameMsg.getCvFrame(), name)
                    allPassed = allPassed and tried[name]
                
                if allPassed:
                    if not self.images_captured:
                        leftStereo =  self.board_config['cameras'][self.board_config['stereo_config']['left_cam']]['name']
                        rightStereo = self.board_config['cameras'][self.board_config['stereo_config']['right_cam']]['name']
                        print(f'Left Camera of stereo is {leftStereo} and right Camera of stereo is {rightStereo}')
                        # if not self.test_camera_orientation(syncedMsgs[leftStereo].getCvFrame(), syncedMsgs[rightStereo].getCvFrame()):
                        #     self.show_failed_orientation()

                    self.images_captured += 1
                    self.images_captured_polygon += 1
                    capturing = False
                else:
                    self.show_failed_capture_frame()
                    capturing = False

            # print(f'self.images_captured_polygon  {self.images_captured_polygon}')
            # print(f'self.current_polygon  {self.current_polygon}')
            # print(f'len(self.polygons)  {len(self.polygons)}')

            if self.images_captured_polygon == self.args.count:
                self.images_captured_polygon = 0
                self.current_polygon += 1

                if self.current_polygon == len(self.polygons):
                    finished = True
                    cv2.destroyAllWindows()
                    break


    def capture_images(self):
        finished = False
        capturing = False
        captured_left = False
        captured_right = False
        captured_color = False
        tried_left = False
        tried_right = False
        tried_color = False
        recent_left = None
        recent_right = None
        recent_color = None
        combine_img = None
        start_timer = False
        timer = self.args.captureDelay
        prev_time = None
        curr_time = None
        self.display_name = "left + right + rgb"
        # with self.get_pipeline() as pipeline:
        while not finished:
            current_left  = self.left_camera_queue.tryGet()
            current_right = self.right_camera_queue.tryGet()
            if not self.args.disableRgb:
                current_color = self.rgb_camera_queue.tryGet()
            else:
                current_color = None
            # recent_left = left_frame.getCvFrame()
            # recent_color = cv2.cvtColor(rgb_frame.getCvFrame(), cv2.COLOR_BGR2GRAY)
            if not current_left is None:
                recent_left = current_left
            if not current_right is None:
                recent_right = current_right
            if not current_color is None:
                recent_color = current_color

            if recent_left is None or recent_right is None or (recent_color is None and not self.args.disableRgb):
                print("Continuing...")
                continue

            recent_frames = [('left', recent_left), ('right', recent_right)]
            if not self.args.disableRgb:
                recent_frames.append(('rgb', recent_color))

            key = cv2.waitKey(1)
            if key == 27 or key == ord("q"):
                print("py: Calibration has been interrupted!")
                raise SystemExit(0)
            elif key == ord(" "):
                if debug:
                    print("setting timer true------------------------")
                start_timer = True
                prev_time = time.time()
                timer = self.args.captureDelay

            frame_list = []
            # left_frame = recent_left.getCvFrame()
            # rgb_frame = recent_color.getCvFrame()

            for packet in recent_frames:
                frame = packet[1].getCvFrame()
                # print(packet[0])
                # frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
                if packet[0] == 'rgb':
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                # print(frame.shape)
                if self.polygons is None:
                    self.height, self.width = frame.shape
                    print(self.height, self.width)
                    self.polygons = calibUtils.setPolygonCoordinates(
                        self.height, self.width)

                # if debug:
                #     print("Timestamp difference ---> l & rgb")
                lrgb_time = 0
                if not self.args.disableRgb:
                    lrgb_time = min([abs((recent_left.getTimestamp() - recent_color.getTimestamp()).microseconds), abs((recent_color.getTimestamp() - recent_left.getTimestamp()).microseconds)]) / 1000
                lr_time = min([abs((recent_left.getTimestamp() - recent_right.getTimestamp()).microseconds), abs((recent_right.getTimestamp() - recent_left.getTimestamp()).microseconds)]) / 1000

                if debug:
                    print(f'Timestamp difference between l & RGB ---> {lrgb_time} in microseconds')
                    print(f'Timestamp difference between l & r ---> {lr_time} in microseconds')

                if capturing and lrgb_time < 50 and lr_time < 30:
                    print("Capturing  ------------------------")
                    if packet[0] == 'left' and not tried_left:
                        captured_left = self.parse_frame(frame, packet[0])
                        tried_left = True
                        captured_left_frame = frame.copy()
                    elif packet[0] == 'rgb' and not tried_color and not self.args.disableRgb:
                        captured_color = self.parse_frame(frame, packet[0])
                        tried_color = True
                        captured_color_frame = frame.copy()
                    elif packet[0] == 'right' and not tried_right:
                        captured_right = self.parse_frame(frame, packet[0])
                        tried_right = True
                        captured_right_frame = frame.copy()


                has_success = (packet[0] == "left" and captured_left) or (packet[0] == "right" and captured_right)  or \
                    (packet[0] == "rgb" and captured_color)

                if self.args.invert_v and self.args.invert_h:
                    frame = cv2.flip(frame, -1)
                elif self.args.invert_v:
                    frame = cv2.flip(frame, 0)
                elif self.args.invert_h:
                    frame = cv2.flip(frame, 1)

                cv2.putText(
                    frame,
                    "Polygon Position: {}. Captured {} of {} {} images".format(
                        self.current_polygon + 1, self.images_captured, self.total_images, packet[0]
                    ),
                    (0, 700), cv2.FONT_HERSHEY_TRIPLEX, 1.0, (255, 0, 0)
                )
                if self.polygons is not None:
                    cv2.polylines(
                        frame, np.array([self.polygons[self.current_polygon]]),
                        True, (0, 255, 0) if captured_left else (0, 0, 255), 4
                    )

                small_frame = cv2.resize(
                    frame, (0, 0), fx=self.output_scale_factor, fy=self.output_scale_factor)
                # cv2.imshow(packet.stream_name, small_frame)
                frame_list.append(small_frame)

                if self.args.disableRgb:
                    captured_color = True
                    tried_color = True
                if captured_left and captured_right and captured_color:
                    print("Images captured --> {}".format(self.images_captured))
                    if not self.images_captured:
                        if not self.test_camera_orientation(captured_left_frame, captured_right_frame):
                            self.show_failed_orientation()
                        # if not self.test_camera_orientation(captured_left_frame, captured_color_frame):
                        #     self.show_failed_orientation()

                    self.images_captured += 1
                    self.images_captured_polygon += 1
                    capturing = False
                    tried_left = False
                    tried_right = False
                    tried_color = False
                    captured_left = False
                    captured_right = False
                    captured_color = False
                elif tried_left and tried_right and tried_color:
                    self.show_failed_capture_frame()
                    capturing = False
                    tried_left = False
                    tried_right = False
                    tried_color = False
                    captured_left = False
                    captured_right = False
                    captured_color = False
                    break

                if self.images_captured_polygon == self.args.count:
                    self.images_captured_polygon = 0
                    self.current_polygon += 1

                    if self.current_polygon == len(self.polygons):
                        finished = True
                        cv2.destroyAllWindows()
                        break
            
            if not self.args.disableRgb:
                frame_list[2] = np.pad(frame_list[2], ((40, 0), (0,0)), 'constant', constant_values=0)
                combine_img = np.hstack((frame_list[0], frame_list[1], frame_list[2]))
            else:
                combine_img = np.vstack((frame_list[0], frame_list[1]))
                self.display_name = "left + right"

            if start_timer == True:
                curr_time = time.time()
                if curr_time - prev_time >= 1:
                    prev_time = curr_time
                    timer = timer-1
                if timer <= 0 and start_timer == True:
                    start_timer = False
                    capturing = True
                    print('Statrt capturing...')
                
                image_shape = combine_img.shape
                cv2.putText(combine_img, str(timer),
                        (image_shape[1]//2, image_shape[0]//2), font,
                        7, (0, 255, 255),
                        4, cv2.LINE_AA)
            cv2.imshow(self.display_name, combine_img)
            frame_list.clear()

    def calibrate(self):
        print("Starting image processing")
        stereo_calib = calibUtils.StereoCalibration()
        dest_path = str(Path('resources').absolute())
        self.args.cameraMode = 'perspective' # hardcoded for now
        try:

            # stereo_calib = StereoCalibration()
            print("Starting image processingxxccx")
            print(self.args.squaresX)
            status, result_config = stereo_calib.calibrate(
                                        self.board_config,
                                        self.dataset_path,
                                        self.args.squareSizeCm,
                                        self.args.markerSizeCm,
                                        self.args.squaresX,
                                        self.args.squaresY,
                                        self.args.cameraMode,
                                        self.args.rectifiedDisp) # Turn off enable disp rectify

            calibration_handler = self.device.readCalibration()
            try:
                if self.empty_calibration(calibration_handler):
                    calibration_handler.setBoardInfo(self.board_config['board_config']['name'], self.board_config['board_config']['revision'])
            except:
                pass

            # calibration_handler.set
            error_text = []

            for camera in result_config['cameras'].keys():
                cam_info = result_config['cameras'][camera]
                # log_list.append(self.ccm_selected[cam_info['name']])

                color = green
                reprojection_error_threshold = 1.0
                if cam_info['size'][1] > 720:
                    print(cam_info['size'][1])
                    reprojection_error_threshold = reprojection_error_threshold * cam_info['size'][1] / 720

                if cam_info['name'] == 'rgb':
                    reprojection_error_threshold = 3
                print('Reprojection error threshold -> {}'.format(reprojection_error_threshold))
                
                if cam_info['reprojection_error'] > reprojection_error_threshold:
                    color = red
                    error_text.append("high Reprojection Error")
                text = cam_info['name'] + ' Reprojection Error: ' + format(cam_info['reprojection_error'], '.6f')
                print(text)
                # pygame_render_text(self.screen, text, (vis_x, vis_y), color, 30)

                calibration_handler.setDistortionCoefficients(stringToCam[camera], cam_info['dist_coeff'])
                calibration_handler.setCameraIntrinsics(stringToCam[camera], cam_info['intrinsics'],  cam_info['size'][0], cam_info['size'][1])
                calibration_handler.setFov(stringToCam[camera], cam_info['hfov'])

                if cam_info['hasAutofocus']:
                    calibration_handler.setLensPosition(stringToCam[camera], self.focus_value)

                # log_list.append(self.focusSigma[cam_info['name']])
                # log_list.append(cam_info['reprojection_error'])
                # color = green///
                # epErrorZText 
                if 'extrinsics' in cam_info:

                    if 'to_cam' in cam_info['extrinsics']:
                        right_cam = result_config['cameras'][cam_info['extrinsics']['to_cam']]['name']
                        left_cam = cam_info['name']
                        
                        epipolar_threshold = 0.6

                        if cam_info['extrinsics']['epipolar_error'] > epipolar_threshold:
                            color = red
                            error_text.append("high epipolar error between " + left_cam + " and " + right_cam)
                        elif cam_info['extrinsics']['epipolar_error'] == -1:
                            color = red
                            error_text.append("Epiploar validation failed between " + left_cam + " and " + right_cam)

                        # log_list.append(cam_info['extrinsics']['epipolar_error'])
                        # text = left_cam + "-" + right_cam + ' Avg Epipolar error: ' + format(cam_info['extrinsics']['epipolar_error'], '.6f')
                        # pygame_render_text(self.screen, text, (vis_x, vis_y), color, 30)
                        # vis_y += 30
                        specTranslation = np.array([cam_info['extrinsics']['specTranslation']['x'], cam_info['extrinsics']['specTranslation']['y'], cam_info['extrinsics']['specTranslation']['z']], dtype=np.float32)

                        calibration_handler.setCameraExtrinsics(stringToCam[camera], stringToCam[cam_info['extrinsics']['to_cam']], cam_info['extrinsics']['rotation_matrix'], cam_info['extrinsics']['translation'], specTranslation)
                        if result_config['stereo_config']['left_cam'] == camera and result_config['stereo_config']['right_cam'] == cam_info['extrinsics']['to_cam']:
                            calibration_handler.setStereoLeft(stringToCam[camera], result_config['stereo_config']['rectification_left'])
                            calibration_handler.setStereoRight(stringToCam[cam_info['extrinsics']['to_cam']], result_config['stereo_config']['rectification_right'])
                        elif result_config['stereo_config']['left_cam'] == cam_info['extrinsics']['to_cam'] and result_config['stereo_config']['right_cam'] == camera:                           
                            calibration_handler.setStereoRight(stringToCam[camera], result_config['stereo_config']['rectification_right'])
                            calibration_handler.setStereoLeft(stringToCam[cam_info['extrinsics']['to_cam']], result_config['stereo_config']['rectification_left'])

            if len(error_text) == 0:
                print('Flashing Calibration data into ')
                # print(calib_dest_path)

                eeepromData = calibration_handler.getEepromData()
                print(f'EEPROM VERSION being flashed is  -> {eeepromData.version}')
                eeepromData.version = 7
                print(f'EEPROM VERSION being flashed is  -> {eeepromData.version}')
                mx_serial_id = self.device.getDeviceInfo().getMxId()
                calib_dest_path = dest_path + '/' + mx_serial_id + '.json'
                calibration_handler.eepromToJsonFile(calib_dest_path)
                # try:
                self.device.flashCalibration2(calibration_handler)
                is_write_succesful = True
                # except RuntimeError as e:
                #     is_write_succesful = False
                #     print(e)
                #     print("Writing in except...")
                #     is_write_succesful = self.device.flashCalibration2(calibration_handler)

                if self.args.factoryCalibration:
                    try:
                        self.device.flashFactoryCalibration(calibration_handler)
                        is_write_factory_sucessful = True
                    except RuntimeError:
                        print("flashFactoryCalibration Failed...")
                        is_write_factory_sucessful = False

                if is_write_succesful:
                    

                    """ eepromUnionData = {}
                    calibHandler = self.device.readCalibration2()
                    eepromUnionData['calibrationUser'] = calibHandler.eepromToJson()

                    calibHandler = self.device.readFactoryCalibration()
                    eepromUnionData['calibrationFactory'] = calibHandler.eepromToJson()

                    eepromUnionData['calibrationUserRaw'] = self.device.readCalibrationRaw()
                    eepromUnionData['calibrationFactoryRaw'] = self.device.readFactoryCalibrationRaw()
                    with open(calib_dest_path, "w") as outfile:
                        json.dump(eepromUnionData, outfile, indent=4) """
                    self.device.close()
                    text = "EEPROM written succesfully"
                    resImage = create_blank(900, 512, rgb_color=green)
                    cv2.putText(resImage, text, (10, 250), font, 2, (0, 0, 0), 2)
                    cv2.imshow("Result Image", resImage)
                    cv2.waitKey(0)
                    
                else:
                    self.device.close()
                    text = "EEPROM write Failed!!"
                    resImage = create_blank(900, 512, rgb_color=red)
                    cv2.putText(resImage, text, (10, 250), font, 2, (0, 0, 0), 2)
                    cv2.imshow("Result Image", resImage)
                    cv2.waitKey(0)
                    # return (False, "EEPROM write Failed!!")
            
            else:
                self.device.close()
                print(error_text)
                for text in error_text: 
                # text = error_text[0]                
                    resImage = create_blank(900, 512, rgb_color=red)
                    cv2.putText(resImage, text, (10, 250), font, 2, (0, 0, 0), 2)
                    cv2.imshow("Result Image", resImage)
                    cv2.waitKey(0)
        except Exception as e:
            print(e)
            raise SystemExit(1)

    def run(self):
        if 'capture' in self.args.mode:
            try:
                if Path('dataset').exists():
                    shutil.rmtree('dataset/')
                for cam_id in self.board_config['cameras']:
                    name = self.board_config['cameras'][cam_id]['name']
                    Path("dataset/{}".format(name)).mkdir(parents=True, exist_ok=True)
                
            except OSError:
                traceback.print_exc()
                print("An error occurred trying to create image dataset directories!")
                raise SystemExit(1)
            self.show_info_frame()
            self.capture_images_sync()
        self.dataset_path = str(Path("dataset").absolute())
        if 'process' in self.args.mode:
            self.calibrate()
        print('py: DONE.')


if __name__ == "__main__":
    Main().run()
