import cv2
import numpy as np
from threading import Thread
import struct
import socket
from queue import Queue
import time


class Camera:
    def __init__(self, connection, height, width):
        self.management_connection = connection
        self.frame_chunks = Queue()
        self.frames = Queue()
        self.height = height
        self.width = width
        self.frame_byte_size = self.height * self.width * 3
        self.is_running = False


class Server:
    def __init__(self):
        self.cameras = {}

        self.__height = 480
        self.__width = 640
        self.__frame_byte_length = self.__height * self.__width * 3

        self.__ip = socket.gethostbyname(socket.gethostname())
        self.__port = 5050

        self.__chunk_size = 45000

        self.__management_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__management_connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        self.__management_connection.setblocking(True)
        self.__handle_new_management_connections()

        self.__udp_connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # TODO: frame byte length changes depending on camera.
        self.__udp_connection.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.__frame_byte_length * 2)
        self.__udp_connection.bind((self.__ip, self.__port))

        self.__udp_buffer = Queue()

        self.__add_traffic_to_buffer()
        self.__add_traffic_to_chunk_queues()

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
            self.cameras[ip] = Camera(connection, self.__height, self.__width)
            self.__handle_existing_management_connection(ip)
        else:
            connection.close()

    def __handle_existing_management_connection(self, ip):
        def loop():
            conn = self.cameras[ip].management_connection
            while True:
                request = conn.recv(2)
                if request == b"gr":  # get resolution
                    conn.send(struct.pack(">2H", self.__height, self.__width))
                elif request == b"sr":  # set resolution
                    resolution = struct.unpack(">2H", conn.recv(struct.calcsize(">2H")))
                    self.cameras[ip].height, self.cameras[ip].width = resolution
                elif request == b"ex":  # exit
                    conn.close()
                    del self.cameras[ip]
                elif request == struct.pack(">?", True):
                    self.ready_stream(ip)

                elif request == struct.pack(">?", False):
                    # stop sending frames
                    pass

                # TODO: fill other possible requests

        Thread(target=loop, daemon=True).start()

    def __add_traffic_to_buffer(self):
        def loop():
            while True:
                chunk = self.__udp_connection.recvfrom(struct.calcsize(">H") + self.__chunk_size)
                self.__udp_buffer.put(chunk)

        Thread(target=loop, daemon=True).start()

    def __add_traffic_to_chunk_queues(self):
        def loop():
            while True:
                chunk, addr = self.__udp_buffer.get()
                # print(chunk)
                self.cameras[addr[0]].frame_chunks.put(chunk)

        Thread(target=loop, daemon=True).start()

    def __handle_chunk_queue(self, ip):
        def loop():
            while True:
                frame = b""
                #t = []
                for chunk_number in range(int(self.cameras[ip].frame_byte_size / self.__chunk_size) + 1):
                    data = self.cameras[ip].frame_chunks.get()
                    #t.append(struct.unpack(">H", data[:struct.calcsize(">H")]))
                    frame += data[struct.calcsize(">H"):]
                #print(t)
                #print(len(t))
                self.cameras[ip].frames.put(self.__format_frame(frame, ip))

        Thread(target=loop, daemon=True).start()

    def __format_frame(self, frame, ip):
        return np.reshape(np.frombuffer(frame, dtype=np.uint8), (self.cameras[ip].height, self.cameras[ip].width, 3))

    def __handle_frame_queue(self, ip):
        def loop():
            while True:
                # TODO: save frame to file (.h264/.h265)
                frame = self.cameras[ip].frames.get()
                cv2.waitKey(1)
                cv2.imshow("frame", frame)

        loop()
        # Thread(target=loop, daemon=True).start()

    def ready_stream(self, ip):
        self.__handle_chunk_queue(ip)
        # self.__handle_frame_queue(ip)
        self.cameras[ip].management_connection.send(struct.pack(">?", True))


if __name__ == '__main__':
    server = Server()
    while True:
        if server.cameras == {}:
            continue
        frame = server.cameras["127.0.0.1"].frames.get()
        cv2.waitKey(1)
        cv2.imshow("frame", frame)
