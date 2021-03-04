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
        self.threads = []


class Server:
    def __init__(self):
        self.cameras = {}

        self.__height = 480
        self.__width = 640
        self.__frame_byte_length = self.__height * self.__width * 3

        self.__ip = "192.168.3.6"
        self.__port = 5050

        self.__chunk_size = 25000

        self.__management_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__management_connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        self.__management_connection.setblocking(True)
        self.__handle_new_management_connections()

        self.__udp_connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # TODO: frame byte length changes depending on camera.
        self.__udp_connection.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.__frame_byte_length * 5)
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
                    self.cameras[ip].frame_byte_size = self.cameras[ip].height * self.cameras[ip].width * 3
                elif request == b"gc":  # get chunk_size
                    conn.send(struct.pack(">H", self.__chunk_size))
                elif request == b"ex":  # exit
                    conn.close()
                    del self.cameras[ip]
                elif request == struct.pack(">?", True):  # start stream
                    self.ready_stream(ip)

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
                self.cameras[addr[0]].frame_chunks.put(chunk)

        Thread(target=loop, daemon=True).start()

    def __handle_chunk_queue(self, ip):
        def loop():
            while self.cameras[ip].is_running is True:
                buffer = b""
                # t = []
                number_of_iterations = int((self.cameras[ip].frame_byte_size / self.__chunk_size) + 1)
                chunk_number = 0
                while chunk_number < number_of_iterations:
                    # print(self.cameras[ip].frame_byte_size - len(buffer))
                    data = self.cameras[ip].frame_chunks.get()
                    frame_count = struct.unpack(">H", data[:struct.calcsize(">H")])[0]
                    # t.append(struct.unpack(">H", data[:struct.calcsize(">H")]))
                    buffer += b"\x00" * self.__calculate_chunks(frame_count, chunk_number) \
                              + data[struct.calcsize(">H"):] if frame_count >= chunk_number \
                        else b"\x00" * self.__calculate_chunks(number_of_iterations, chunk_number)
                    chunk_number = frame_count + 1 if frame_count >= chunk_number else number_of_iterations
                # The buffer is to large when the final chunk disappears and it is replaced with a full chunk of
                # darkness even tough the last bit of the frame doesnt have the same size as the inserted chunk.
                buffer = buffer[:self.cameras[ip].frame_byte_size]
                # print(3*1280*720, len(buffer))
                # print(t)
                # print(len(t))
                self.cameras[ip].frames.put(self.__format_frame(buffer, ip))

        t = Thread(target=loop, daemon=True)
        t.start()
        self.cameras[ip].threads.append(t)

    def __calculate_chunks(self, x, y):
        return self.__chunk_size * (x - y)

    def __format_frame(self, frame, ip):
        return np.reshape(np.frombuffer(frame, dtype=np.uint8), (self.cameras[ip].height, self.cameras[ip].width, 3))

    def __handle_frame_queue(self, ip):
        def loop():
            while self.cameras[ip].is_running is True:
                if self.cameras[ip].frames.empty():
                    continue
                # TODO: save frame to file (.h264/.h265)

        # t = Thread(target=loop, daemon=True)
        # t.start()
        # self.cameras[ip].threads.append(t)

    def ready_stream(self, ip):
        self.cameras[ip].is_running = True
        self.__handle_chunk_queue(ip)
        # self.__handle_frame_queue(ip)
        self.cameras[ip].management_connection.send(struct.pack(">?", True))

    def stop_stream(self, ip):
        if self.cameras[ip].is_running is True:
            self.cameras[ip].is_running = False
        self.join_camera_threads(ip)
        self.cameras[ip].management_connection.send(struct.pack(">?", False))
        self.cameras[ip].management_connection.close()
        del self.cameras[ip]

    def join_camera_threads(self, ip):
        for thread in self.cameras[ip].threads:
            thread.join()


if __name__ == '__main__':
    server = Server()

    def test():
        time.sleep(10)
        server.stop_stream("192.168.3.6")

    Thread(target=test, daemon=True).start()

    while True:
        if server.cameras == {}:
            continue
        frame = server.cameras["192.168.3.6"].frames.get()
        cv2.waitKey(1)
        cv2.imshow("frame", frame)
