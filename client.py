import cv2
import numpy as np
from threading import Thread
import struct
from time import sleep
import socket
from queue import Queue


class Capture:
    def __init__(self, resolution):
        self.__is_running = False

        self.__height, self.__width = resolution
        # frame.shape = (height, width, 3)
        self.__frame = np.empty((self.__height, self.__width, 3))

    def get_frame(self):
        return self.__frame

    def is_running(self):
        return self.__is_running

    def start(self):
        self.__is_running = True
        cap = cv2.VideoCapture(0)

        def loop():
            while self.__is_running:
                ret, frame = cap.read()
                frame = cv2.resize(frame, (self.__width, self.__height))
                frame = cv2.flip(frame, 1)
                self.__frame = frame
            cap.release()

        Thread(target=loop, daemon=True).start()

    def stop(self):
        self.__is_running = False


class Client:
    def __init__(self):
        self.__buffer = Queue()

        # TODO: make .conf with custom resolution option
        self.__use_custom_resolution = False
        self.__resolution = None

        self.__ip = socket.gethostbyname(socket.gethostname())  # TODO: change with netifaces
        self.__port = 5050
        self.__identifier = b"c"  # camera

        self.__management_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__management_connection.setblocking(True)
        self.__initialize_management_connection()

        self.__udp_connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def __initialize_management_connection(self):
        self.__management_connection.connect((self.__ip, self.__port))
        self.__management_connection.send(self.__identifier)
        self.__request_resolution()

    def __request_resolution(self):
        if self.__use_custom_resolution is False:
            self.__management_connection.send(b"r")  # request resolution
            resolution = struct.unpack(">2H", self.__management_connection.recv(struct.calcsize(">2H")))
            self.__resolution = resolution
            print(resolution)
        else:
            self.__resolution = (480, 640)


client = Client()
