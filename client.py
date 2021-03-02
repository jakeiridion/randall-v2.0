import cv2
from threading import Thread
import struct
import time
import socket
from queue import Queue
from datetime import datetime
import configparser

threads = []


def join_all_threads():
    for thread in threads:
        thread.join()


class Config:
    def __init__(self):
        client_config = configparser.ConfigParser()
        client_config.read("client.ini")
        # Network Variables
        self.ip = client_config["Network"]["IP"]
        self.port = client_config["Network"].getint("PORT")
        self.udp_receive_buffer = client_config["Network"].getint("UdpReceiveBuffer")
        self.chunk_size = client_config["Network"].getint("ChunkSize")
        self.wait_after_frame = client_config["Network"].getfloat("WaitAfterFrame")
        # Camera Variables
        self.capture_device = client_config["VideoCapture"].getint("CaptureDevice")
        self.use_custom_resolution = client_config["VideoCapture"].getboolean("UseCustomResolution")
        self.custom_frame_height = client_config["VideoCapture"].getint("CustomFrameHeight")
        self.custom_frame_width = client_config["VideoCapture"].getint("CustomFrameWidth")
        # Check Values
        self.__check_network_settings()
        self.__check_video_capture_settings()

    def __check_network_settings(self):
        try:
            socket.inet_aton(self.ip)
        except socket.error:
            raise Exception("BAD IP ADDRESS")

        if self.port > 65535 or self.port < 1:
            raise Exception("BAD PORT")

        if self.udp_receive_buffer < 1:
            raise Exception("BAD UDP RECEIVE BUFFER")

        if self.chunk_size < 1 or self.chunk_size > 65500:
            raise Exception("BAD CHUNK SIZE")

        if self.wait_after_frame < 0:
            raise Exception("BAD WAIT VALUE")

    def __check_video_capture_settings(self):
        if self.capture_device < 0:
            raise Exception("BAD CAPTURE DEVICE")

        if self.custom_frame_height < 0 and self.use_custom_resolution:
            raise Exception("BAD FRAME HEIGHT")

        if self.custom_frame_width < 0 and self.use_custom_resolution:
            raise Exception("BAD FRAME WIDTH")


config = Config()


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
        cap = cv2.VideoCapture(config.capture_device)

        def loop():
            while self.__is_running:
                ret, frame = cap.read()
                frame = cv2.resize(frame, (self.__width, self.__height))
                frame = cv2.flip(frame, 1)
                self.__buffer.put(frame)
            cap.release()

        t = Thread(target=loop, daemon=True).start()
        threads.append(t)

    def stop(self):
        self.__is_running = False


class Client:
    def __init__(self):
        self.__ip = config.ip
        self.__port = config.port
        self.__identifier = b"c"  # camera

        self.__management_connection = self.__create_management_connection()
        self.__management_connection.setblocking(True)
        self.__initialize_management_connection()

        self.__height, self.__width = (config.custom_frame_height, config.custom_frame_width)\
            if config.use_custom_resolution else self.__request_resolution()
        self.__update_server_resolution_if_necessary()

        self.__frame_byte_length = self.__height * self.__width * 3
        self.__chunk_size = config.chunk_size

        self.capture = Capture((self.__height, self.__width))

        self.__udp_connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.__udp_connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 7456540)

        self.formatted_frames = Queue()

    def __create_management_connection(self):
        # TODO: make sure a connection to the server lan is established.
        while True:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((self.__ip, self.__port))
            if result == 0:
                return sock
            sock.close()
            time.sleep(5)

    def __initialize_management_connection(self):
        self.__management_connection.send(self.__identifier)
        # TODO: Receive Chunk size

    def __request_resolution(self):
        if not config.use_custom_resolution:
            self.__management_connection.send(b"gr")  # get resolution
            resolution = struct.unpack(">2H", self.__management_connection.recv(struct.calcsize(">2H")))
            return resolution

    def __update_server_resolution_if_necessary(self):
        if config.use_custom_resolution:
            self.__management_connection.send(b"sr")  # set resolution
            self.__management_connection.send(struct.pack(">2H", self.__height, self.__width))

    def listen_for_commands(self):
        while True:
            command = self.__management_connection.recv(1)
            if command == struct.pack(">?", True):  # Start stream
                self.__start_stream()
            elif command == struct.pack(">?", False):  # Stop Stream
                self.__stop_stream()
                break

    def request_stream_start(self):
        self.__management_connection.send(struct.pack(">?", True))

    def __start_stream(self):
        self.capture.start()
        self.__start_record_timer()
        self.__start_formating_frames()

        def loop():
            while self.capture.is_running():
                frame = self.formatted_frames.get()
                for chunk_number in range(int(self.__frame_byte_length / self.__chunk_size) + 1):
                    self.__udp_connection.sendto(
                        struct.pack(">H", chunk_number) + frame[
                                                          self.__chunk_size * chunk_number:self.__chunk_size * (
                                                                  chunk_number + 1)], (self.__ip, self.__port))
                    time.sleep(config.wait_after_frame)

        t = Thread(target=loop, daemon=True).start()
        threads.append(t)

    def __start_formating_frames(self):
        def loop():
            while self.capture.is_running():
                frame = self.capture.get_frame()
                # Current day:
                frame = cv2.rectangle(frame, (10, self.__height - 5), (195, self.__height - 25), (0, 0, 0), -1)
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                frame = cv2.putText(frame, now, (10, self.__height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                    (255, 255, 255), 1)

                # Record time:
                # TODO: Make sure the rec timer is leveled with the date.
                frame = cv2.rectangle(frame, ((self.__width - 10) - 95, self.__height - 5),
                                      (self.__width - 10, self.__height - 25), (0, 0, 0), -1)
                frame = cv2.putText(frame, self.capture.record_time, ((self.__width - 10) - 95, self.__height - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                frame = frame.tobytes()
                self.formatted_frames.put(frame)

        t = Thread(target=loop, daemon=True).start()
        threads.append(t)

    def __start_record_timer(self):
        start_time = datetime.now()

        def loop():
            while self.capture.is_running():
                record_time = datetime.now() - start_time
                days = record_time.days
                hours, rem = divmod(record_time.seconds, 3600)
                minutes, seconds = divmod(rem, 60)
                self.capture.record_time = f"{days:02d}:{hours:02d}:{minutes:02d}:{seconds:02d}"
                if self.capture.record_time == "99:23:59:59":  # max REC timer value
                    break
                time.sleep(1)
        t = Thread(target=loop, daemon=True).start()
        threads.append(t)

    def __stop_stream(self):
        self.capture.stop()
        join_all_threads()

    def start_client(self):
        self.request_stream_start()
        self.listen_for_commands()


if __name__ == '__main__':
    client = Client()
    client.start_client()
