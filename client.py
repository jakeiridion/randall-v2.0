import cv2
import numpy as np
from threading import Thread
import struct
import time
import socket
from queue import Queue
from datetime import datetime, timedelta

threads = []


class Capture:
    def __init__(self, resolution):
        self.__is_running = False

        self.__height, self.__width = resolution
        # frame.shape = (height, width, 3)

        self.__buffer = Queue()
        self.record_time = ""

    def get_frame(self):
        # TODO: maybe set timeouts
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

        t = Thread(target=loop, daemon=True)
        t.start()
        threads.append(t)

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
        self.__chunk_size = 65000

        self.capture = Capture((self.__height, self.__width))

        self.__udp_connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.__udp_connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, self.__frame_byte_length * 5)

    def __initialize_management_connection(self):
        # self.__try_connect()
        self.__management_connection.connect((self.__ip, self.__port))
        self.__management_connection.send(self.__identifier)

    def __try_connect(self):
        connected = False
        while connected is False:
            try:
                self.__management_connection.connect((self.__ip, self.__port))
            except (ConnectionRefusedError, OSError):
                time.sleep(5)
                continue
            connected = True

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
            command = self.__management_connection.recv(1)
            if command == struct.pack(">?", True):  # Start stream
                self.__start_stream()
            elif command == struct.pack(">?", False):  # Stop Stream
                self.__stop_stream()
                break

    def __join_all_threads(self):
        for thread in threads:
            thread.join()

    def request_stream_start(self):
        self.__management_connection.send(struct.pack(">?", True))

    def __start_stream(self):
        def loop():
            self.capture.start()
            self.__start_record_timer()
            while self.capture.is_running():
                frame = self.capture.get_frame()
                # frame_in_bytes = frame.tobytes()
                frame_in_bytes = self.__format_frame(frame)
                for chunk_number in range(int(self.__frame_byte_length / self.__chunk_size) + 1):
                    self.__udp_connection.sendto(
                        struct.pack(">H", chunk_number) + frame_in_bytes[
                                                          self.__chunk_size * chunk_number:self.__chunk_size * (
                                                                  chunk_number + 1)],
                        (self.__ip, self.__port))
                    # time.sleep(0.0001)

        t = Thread(target=loop, daemon=True)
        t.start()
        threads.append(t)

    def __format_frame(self, frame):
        # Current day:
        frame = cv2.rectangle(frame, (10, self.__height - 5), (195, self.__height - 25), (0, 0, 0), -1)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        frame = cv2.putText(frame, now, (10, self.__height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Record time:
        frame = cv2.rectangle(frame, ((self.__width - 10) - 95, self.__height - 5),
                              (self.__width - 10, self.__height - 25), (0, 0, 0), -1)
        frame = cv2.putText(frame, self.capture.record_time, ((self.__width - 10) - 95, self.__height - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        return frame.tobytes()

    def __start_record_timer(self):
        start_time = datetime.now()

        def loop():
            while self.capture.is_running():
                record_time = datetime.now() - start_time
                days = record_time.days
                hours, rem = divmod(record_time.seconds, 3600)
                minutes, seconds = divmod(rem, 60)
                self.capture.record_time = f"{days:02d}:{hours:02d}:{minutes:02d}:{seconds:02d}"
                time.sleep(1)
        t = Thread(target=loop, daemon=True).start()
        threads.append(t)

    def __stop_stream(self):
        self.capture.stop()
        self.__join_all_threads()

    def start_client(self):
        self.request_stream_start()
        self.listen_for_commands()


if __name__ == '__main__':
    client = Client()
    client.start_client()
