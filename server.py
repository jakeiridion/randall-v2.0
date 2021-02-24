import cv2
import numpy as np
from threading import Thread
import struct
import socket
from queue import Queue


class Camera:
    def __init__(self, connection, height, width):
        self.management_connection = connection
        self.frame_chunks = Queue()
        self.frames = Queue()
        self.height = height
        self.width = width


class Server:
    def __init__(self):
        self.__cameras = {}

        self.__height = 480
        self.__width = 640
        self.__frame_byte_length = self.__height * self.__width * 3

        self.__ip = socket.gethostbyname(socket.gethostname())
        self.__port = 5050

        self.__management_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__management_connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        self.__management_connection.setblocking(True)
        self.__handle_new_management_connections()

        self.__udp_connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # TODO: frame byte length changes depending on camera.
        self.__udp_connection.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.__frame_byte_length*4)

    def __handle_new_management_connections(self):
        self.__management_connection.bind((self.__ip, self.__port))
        self.__management_connection.listen()

        def loop():
            while True:
                conn, addr = self.__management_connection.accept()
                identifier = conn.recv(1)
                self.__handle_identifier(identifier, conn, addr[0])

        Thread(target=loop, daemon=True).start()

    def __handle_identifier(self, identifier, connection, ip):
        if identifier == b"c":  # camera
            self.__cameras[ip] = Camera(connection, self.__height, self.__width)
            self.__handle_existing_management_connection(ip)
        else:
            connection.close()

    def __handle_existing_management_connection(self, ip):
        def loop():
            conn = self.__cameras[ip].management_connection
            while True:
                request = conn.recv(2)
                if request == b"gr":  # get resolution
                    conn.send(struct.pack(">2H", self.__height, self.__width))
                elif request == b"sr":  # set resolution
                    resolution = struct.unpack(">2H", conn.recv(struct.calcsize(">2H")))
                    self.__cameras[ip].height, self.__cameras[ip].width = resolution
                elif request == b"ex":  # exit
                    conn.close()
                    del self.__cameras[ip]
                elif request == struct.pack(">?", True):
                    # start sending frames
                    pass
                elif request == struct.pack(">?", False):
                    # stop sending frames
                    pass

                # TODO: fill other possible requests

        Thread(target=loop, daemon=True).start()


if __name__ == '__main__':
    server = Server()
    while True:
        pass
