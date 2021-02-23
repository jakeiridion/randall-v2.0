import cv2
import numpy as np
from threading import Thread
import struct
import socket
from queue import Queue


class Server:
    def __init__(self):
        self.__cameras = {}

        self.__height = 480
        self.__width = 640

        self.__ip = socket.gethostbyname(socket.gethostname())
        self.__port = 5050

        self.__management_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__management_connection.setblocking(True)
        self.__handle_new_management_connections()

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
        if identifier == b"c":
            # cameras[ip] = (identifier, management_connection_to_camera, chunk_queue, frame_queue)
            self.__cameras[ip] = (identifier, connection, Queue(), Queue())
            self.__handle_existing_management_connection(ip)
        else:
            connection.close()

    def __handle_existing_management_connection(self, ip):
        def loop():
            conn = self.__cameras[ip][1]
            while True:
                request = conn.recv(1)
                if request == b"r":  # request for resolution
                    conn.send(struct.pack(">2H", self.__height, self.__width))
                # TODO: fill other possible requests

        Thread(target=loop, daemon=True).start()


server = Server()
while True:
    pass
