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

        self.__buffer = Queue()

    def get_frame(self):
        return self.__buffer.get()

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
                self.__buffer.put(frame)
            cap.release()

        Thread(target=loop, daemon=True).start()

    def stop(self):
        self.__is_running = False


class Client:
    def __init__(self):
        self.__ip = socket.gethostbyname(socket.gethostname())  # TODO: change with netifaces
        self.__port = 5050
        self.__identifier = b"c"  # camera

        self.__management_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__management_connection.setblocking(True)
        self.__initialize_management_connection()

        self.__buffer = Queue()

        self.__use_custom_resolution = False
        self.__height, self.__width = self.__request_resolution()
        self.__frame_byte_length = self.__height * self.__width * 3

        self.__udp_connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.__udp_connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, self.__frame_byte_length * 4)

        self.dtype = np.dtype(np.uint8)

    def __initialize_management_connection(self):
        self.__management_connection.connect((self.__ip, self.__port))
        self.__management_connection.send(self.__identifier)

    def __request_resolution(self):
        if self.__use_custom_resolution is False:
            self.__management_connection.send(b"gr")  # get resolution
            resolution = struct.unpack(">2H", self.__management_connection.recv(struct.calcsize(">2H")))
            height, width = resolution
        else:
            # TODO: make .conf with custom resolution option
            height, width = (480, 640)
            self.__management_connection.send(b"sr")  # set resolution
            self.__management_connection.send(struct.pack(">2H", height, width))
        print(height, width)
        return height, width

    def get_resolution(self):
        return self.__height, self.__width


if __name__ == '__main__':
    client = Client()
    capture = Capture(client.get_resolution())
    capture.start()

    while capture.is_running():
        frame = capture.get_frame()
        cv2.waitKey(1)
        cv2.imshow("frame", frame)
