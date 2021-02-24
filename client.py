import cv2
import numpy as np
from threading import Thread
import struct
import time
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

        self.__use_custom_resolution = False
        self.__height, self.__width = self.__request_resolution()

        self.__frame_byte_length = self.__height * self.__width * 3
        self.__chunk_size = 45000

        self.capture = Capture((self.__height, self.__width))

        self.__udp_connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.__udp_connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, self.__frame_byte_length * 2)

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

    def listen_for_commands(self):
        while True:
            command = self.__management_connection.recv(2)
            if command == struct.pack(">?", True):  # Start stream
                print("started")
                self.start_stream()

    def request_stream_start(self):
        self.__management_connection.send(struct.pack(">?", True))

    def start_stream(self):
        def loop():
            self.capture.start()
            while self.capture.is_running():
                frame = self.capture.get_frame()
                frame_in_bytes = frame.tobytes()
                for chunk_number in range(int(self.__frame_byte_length / self.__chunk_size) + 1):
                    self.__udp_connection.sendto(
                        struct.pack(">H", chunk_number) + frame_in_bytes[
                                                          self.__chunk_size * chunk_number:self.__chunk_size * (
                                                                      chunk_number + 1)],
                        (self.__ip, self.__port))
                    time.sleep(0.0001)

        Thread(target=loop, daemon=True).start()


if __name__ == '__main__':
    client = Client()
    client.request_stream_start()
    client.listen_for_commands()
