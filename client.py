import cv2
from threading import Thread
import struct
import time
import socket
from queue import Queue
from datetime import datetime
import configparser
import logging
import sys


def initiate_logger():
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler("client.log")
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s:%(name)s:%(levelname)s:%(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(formatter)
    log.addHandler(file_handler)
    return log


logger = initiate_logger()
threads = []


def join_all_threads():
    logger.debug("joining threads...")
    for thread in threads:
        logger.debug(f"joining thread: {thread}")
        thread.join()
    logger.debug("all threads joined.")


class Config:
    def __init__(self):
        client_config = configparser.ConfigParser()
        client_config.read("client.ini")
        # Default Variables
        self.debug_mode = client_config["DEVELOPER"].getboolean("DebugMode")
        self.__handle_debug_mode()
        logger.info("Loading Configuration file...")
        # Network Variables
        logger.debug("Loading Network settings...")
        self.ip = client_config["Network"]["ServerIP"]
        self.port = client_config["Network"].getint("ServerPORT")
        self.udp_receive_buffer = client_config["Network"].getint("UdpReceiveBuffer")
        self.wait_after_frame = client_config["Network"].getfloat("WaitAfterFrame")
        logger.debug("Network settings loaded.")
        # Camera Variables
        logger.debug("Loading Camera settings.")
        self.capture_device = client_config["VideoCapture"].getint("CaptureDevice")
        self.use_custom_resolution = client_config["VideoCapture"].getboolean("UseCustomResolution")
        self.__log_custom_resolution_mode()
        self.custom_frame_height = client_config["VideoCapture"].getint("CustomFrameHeight")
        self.custom_frame_width = client_config["VideoCapture"].getint("CustomFrameWidth")
        logger.debug("Camera settings loaded.")
        # Check Values
        logger.debug("verifying settings.")
        self.__check_network_settings()
        self.__check_video_capture_settings()
        # Log
        logger.info("Configuration file loaded.")

    def __handle_debug_mode(self):
        if self.debug_mode:
            global logger
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter("%(asctime)s:%(name)s:%(levelname)s:%(message)s", datefmt="%Y-%m-%d %H:%M:%S")
            stream_handler.setFormatter(formatter)
            logger.addHandler(stream_handler)
            logger.info("-" * 10 + "APPLICATION STARTED" + "-" * 10)
            logger.debug("DEBUG MODE ACTIVATED")

    def __log_custom_resolution_mode(self):
        if self.use_custom_resolution:
            logger.debug("use custom resolution: enabled")
        else:
            logger.debug("use custom resolution: disabled")

    def __check_network_settings(self):
        logger.debug("verifying ServerIP.")
        try:
            socket.inet_aton(self.ip)
        except socket.error:
            logger.exception("Bad IP Address detected in config.")
            raise Exception("BAD IP ADDRESS")

        logger.debug("verifying ServerPORT.")
        if self.port > 65535 or self.port < 1:
            logger.error("Bad Port detected in config. %s", "Allowed ports: 1 < port < 65535")
            raise Exception("BAD PORT")

        logger.debug("verifying UdpReceiveBuffer.")
        if self.udp_receive_buffer < 1:
            logger.error("Bad udp receive value in config. %s", "Value can not be negative.")
            raise Exception("BAD UDP RECEIVE BUFFER")

        logger.debug("verifying WaitAfterFrame.")
        if self.wait_after_frame < 0:
            logger.error("Bad wait value in config. %s", "Value can not be negative.")
            raise Exception("BAD WAIT VALUE")

    def __check_video_capture_settings(self):
        logger.debug("verifying CaptureDevice.")
        self.__check_capture_device()

        if self.use_custom_resolution:
            logger.debug("verifying CustomFrameHeight.")
            if self.custom_frame_height < 0:
                logger.error("Bad frame height. %s", "Value can not be negative.")
                raise Exception("BAD FRAME HEIGHT")

            logger.debug("verifying CustomFrameWidth.")
            if self.custom_frame_width < 0:
                logger.error("Bad frame width. %s", "Value can not be negative.")
                raise Exception("BAD FRAME WIDTH")

    def __check_capture_device(self):
        if self.capture_device < 0:
            logger.error("Bad capture device value. %s", "Value can not be negative.")
            raise Exception("BAD CAPTURE DEVICE")

        cap = cv2.VideoCapture(self.capture_device)
        if cap.isOpened():
            cap.release()
        else:
            logger.error("Capture Device failed to initialize.")
            sys.exit(1)


config = Config()


class Capture:
    def __init__(self, resolution):
        logger.debug("Initiating Capture Class...")
        self.__is_running = False

        self.__height, self.__width = resolution
        # frame.shape = (height, width, 3)

        self.__buffer = Queue()
        self.record_time = ""
        logger.debug("Capture Class initiated.")

    def get_frame(self):
        # TODO: only work while camera is plugged in.
        return self.__buffer.get()

    def is_running(self):
        return self.__is_running

    def start(self):
        logger.debug("starting Video Capture...")
        self.__is_running = True
        cap = cv2.VideoCapture(config.capture_device)

        def loop():
            while self.__is_running:
                ret, frame = cap.read()
                frame = cv2.resize(frame, (self.__width, self.__height))
                frame = cv2.flip(frame, 1)
                self.__buffer.put(frame)
            cap.release()
            logger.debug("Video Capture stopped.")

        t = Thread(target=loop, daemon=True)
        t.start()
        threads.append(t)

    def stop(self):
        logger.debug("stopping Video Capture...")
        self.__is_running = False


class Client:
    def __init__(self):
        logger.debug("Initiating Client Class...")
        self.__ip = config.ip
        self.__port = config.port
        self.__identifier = b"c"  # camera

        self.__management_connection = self.__create_management_connection()
        self.__management_connection.setblocking(True)
        self.__initialize_management_connection()

        self.__height, self.__width = (config.custom_frame_height, config.custom_frame_width) \
            if config.use_custom_resolution else self.__request_resolution()
        self.__update_server_resolution_if_necessary()
        logger.debug("resolution set.")

        self.__frame_byte_length = self.__height * self.__width * 3
        self.__chunk_size = self.__request_chunk_size()
        logger.debug("chunk size set.")

        self.capture = Capture((self.__height, self.__width))

        logger.debug("creating udp connection...")
        self.__udp_connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.__udp_connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 7456540)
        logger.debug("udp connection created.")

        self.formatted_frames = Queue()
        logger.debug("Client Class initiated.")

    def __create_management_connection(self):
        # TODO: make sure a connection to the server lan is established.
        logger.debug("Creating management connection...")
        while True:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((self.__ip, self.__port))
            if result == 0:
                logger.debug("Management connection created.")
                return sock
            sock.close()
            time.sleep(5)

    def __initialize_management_connection(self):
        logger.debug("Initialize management connection.")
        self.__management_connection.send(self.__identifier)

    def __request_resolution(self):
        if not config.use_custom_resolution:
            logger.debug("request server resolution...")
            self.__management_connection.send(b"gr")  # get resolution
            logger.debug("set resolution to server resolution.")
            resolution = struct.unpack(">2H", self.__management_connection.recv(struct.calcsize(">2H")))
            return resolution

    def __request_chunk_size(self):
        logger.debug("request chunk size...")
        self.__management_connection.send(b"gc")  # get chunk_size
        return struct.unpack(">H", self.__management_connection.recv(struct.calcsize(">H")))[0]

    def __update_server_resolution_if_necessary(self):
        if config.use_custom_resolution:
            self.__management_connection.send(b"sr")  # set resolution
            self.__management_connection.send(struct.pack(">2H", self.__height, self.__width))
            logger.debug("Send custom resolution to server.")

    def listen_for_commands(self):
        logger.info("listening for commands...")
        while True:
            command = self.__management_connection.recv(1)
            logger.debug(f"Command received: {command}")
            if command == struct.pack(">?", True):  # Start stream
                logger.info("starting stream...")
                self.__start_stream()
            elif command == struct.pack(">?", False):  # Stop Stream
                self.__stop_stream()
                break
        logger.debug("stop listening for commands.")

    def request_stream_start(self):
        logger.info("requesting stream start.")
        self.__management_connection.send(struct.pack(">?", True))

    def __start_stream(self):
        logger.debug("initializing stream...")
        self.capture.start()
        self.__start_record_timer()
        self.__start_formatting_frames()
        logger.debug("stream initialized. %s", "streaming...")

        def loop():
            while self.capture.is_running():
                frame = self.formatted_frames.get()
                for chunk_number in range(int(self.__frame_byte_length / self.__chunk_size) + 1):
                    self.__udp_connection.sendto(
                        struct.pack(">H", chunk_number) + frame[
                                                          self.__chunk_size * chunk_number:self.__chunk_size * (
                                                                  chunk_number + 1)], (self.__ip, self.__port))
                    time.sleep(config.wait_after_frame)
            logger.info("stream stopped.")

        t = Thread(target=loop, daemon=True)
        t.start()
        threads.append(t)

    def __start_formatting_frames(self):
        logger.debug("starting frame formatting.")

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
            logger.debug("stop frame formatting.")

        t = Thread(target=loop, daemon=True)
        t.start()
        threads.append(t)

    def __start_record_timer(self):
        logger.debug("starting record timer.")
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
            logger.debug("stop record timer.")

        t = Thread(target=loop, daemon=True)
        t.start()
        threads.append(t)

    def __stop_stream(self):
        logger.info("stopping stream...")
        self.capture.stop()
        join_all_threads()

    def start_client(self):
        logger.info("starting client...")
        self.request_stream_start()
        self.listen_for_commands()
        logger.info("closing client.")


if __name__ == '__main__':
    client = Client()
    client.start_client()
    logger.info("-" * 10 + "APPLICATION STOPPED" + "-" * 10)
