import cv2
import multiprocessing as mp
from threading import Thread
import struct
import ctypes
import time
import socket
from datetime import datetime
import configparser
import logging
from logging.handlers import RotatingFileHandler
import sys
import signal
import math


def initiate_logger():
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)
    file_handler = RotatingFileHandler("client.log", maxBytes=10_000_000, backupCount=1)
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s:%(name)s:%(levelname)s:%(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(formatter)
    log.addHandler(file_handler)
    return log


logger = initiate_logger()
processes_threads = []


def join_all_processes_threads():
    logger.debug("joining processes/threads...")
    for item in processes_threads:
        logger.debug(f"joining thread: {item}") if type(item) == type(Thread()) \
            else logger.debug(f"joining process: {item}")
        item.join()
        logger.debug(f"thread joined: {item}") if type(item) == type(Thread()) \
            else logger.debug(f"process joined: {item}")
    logger.debug("all threads/processes joined.")
    processes_threads.clear()


class Config:
    def __init__(self):
        client_config = configparser.ConfigParser()
        client_config.read("client.ini")
        # Default Variables
        self.__debug_mode = client_config["DEVELOPER"].getboolean("DebugMode")
        self.__handle_debug_mode()
        logger.info("Loading Configuration file...")
        # Network Variables
        logger.debug("Loading Network settings...")
        self.ip = client_config["Network"]["ServerIP"]
        self.port = client_config["Network"].getint("ServerPORT")
        self.udp_send_buffer = client_config["Network"].getint("UdpSendBuffer")
        self.wait_after_chunk = client_config["Network"].getfloat("WaitAfterChunk")
        self.wait_after_frame = client_config["Network"].getfloat("WaitAfterFrame")
        self.retry_after_server_crash = client_config["Network"].getint("RetryAfterServerCrash")
        logger.debug("Network settings loaded.")
        # Camera Variables
        logger.debug("Loading Camera settings...")
        self.capture_device = client_config["VideoCapture"].getint("CaptureDevice")
        self.use_custom_resolution = client_config["VideoCapture"].getboolean("UseCustomResolution")
        self.__log_custom_resolution_mode()
        self.custom_frame_height = client_config["VideoCapture"].getint("CustomFrameHeight")
        self.custom_frame_width = client_config["VideoCapture"].getint("CustomFrameWidth")
        logger.debug("Camera settings loaded.")
        # Check Values
        logger.debug("verifying settings...")
        self.__check_network_settings()
        self.__check_video_capture_settings()
        logger.debug("settings verified.")
        logger.info("Configuration file loaded.")

    def __handle_debug_mode(self):
        if self.__debug_mode:
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

        logger.debug("verifying UdpSendBuffer.")
        if self.udp_send_buffer < 1:
            logger.error("Bad udp receive value in config. %s", "Value can not be negative.")
            raise Exception("BAD UDP SEND BUFFER")

        logger.debug("verifying WaitAfterChunk.")
        if self.wait_after_chunk < 0:
            logger.error("Bad wait value in config. %s", "Value can not be negative.")
            raise Exception("BAD WAIT VALUE")

        logger.debug("verifying WaitAfterFrame.")
        if self.wait_after_frame < 0:
            logger.error("Bad wait value in config. %s", "Value can not be negative.")
            raise Exception("BAD WAIT VALUE")

        logger.debug("verifying RetryAfterCrash")
        if self.retry_after_server_crash < 0:
            logger.error("Bad crash wait value in config. %s", "Value can not be negative.")
            raise Exception("BAD CRASH WAIT VALUE")

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
        logger.debug("Initializing Capture Class...")
        self.is_running = mp.Value(ctypes.c_bool, False)
        self.height, self.width = resolution  # frame.shape = (height, width, 3)
        self.__record_timer = mp.Manager().Value(ctypes.c_wchar_p, "00:00:00:00")
        logger.debug("Capture Class initialized.")

    def start(self, pipe_in):
        frame_pipe_out, frame_pipe_in = mp.Pipe(False)
        self.__start_capture_thread(frame_pipe_in)
        self.__start_record_timer_process()
        self.__start_frame_formatting_process(frame_pipe_out, pipe_in)

    def __start_capture_thread(self, pipe_in):
        def loop(log, is_running, capture_device, width, height, pipe):
            log.debug("starting Video Capture...")
            is_running.value = True
            cap = cv2.VideoCapture(capture_device)
            while is_running.value:
                ret, frame = cap.read()
                frame = cv2.flip(frame, 1)
                frame = cv2.resize(frame, (width, height))
                pipe.send(frame)
            cap.release()
            log.debug("Video Capture stopped.")

        t = Thread(target=loop,
                   args=[logger, self.is_running, config.capture_device, self.width, self.height, pipe_in],
                   daemon=True)
        t.start()
        processes_threads.append(t)

    def __start_record_timer_process(self):
        def loop(log, is_running, record_timer):
            log.debug("starting record timer.")
            start_time = datetime.now()
            while is_running.value:
                rc = datetime.now() - start_time
                days = rc.days
                hours, rem = divmod(rc.seconds, 3600)
                minutes, seconds = divmod(rem, 60)
                record_timer.value = f"{days:02d}:{hours:02d}:{minutes:02d}:{seconds:02d}"
                if rc == "99:23:59:59":  # max REC timer value
                    break
                time.sleep(1)
            log.debug("stop record timer.")

        p = mp.Process(target=loop, args=(logger, self.is_running, self.__record_timer))
        p.start()
        processes_threads.append(p)

    def __start_frame_formatting_process(self, pipe_out, pipe_in):
        def loop(log, is_running, pipe_o, pipe_i, height, width, record_timer):
            log.debug("starting frame formatting.")
            while is_running.value:
                frame = pipe_o.recv()
                # Current day:
                frame = cv2.rectangle(frame, (10, height - 5), (195, height - 25), (0, 0, 0), -1)
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                frame = cv2.putText(frame, now, (10, height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                    (255, 255, 255), 1)

                # Record time:
                frame = cv2.rectangle(frame, ((width - 10) - 95, height - 5),
                                      (width - 10, height - 25), (0, 0, 0), -1)
                frame = cv2.putText(frame, record_timer.value, ((width - 10) - 95, height - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                pipe_i.send_bytes(frame.tobytes())
            log.debug("stop frame formatting.")

        p = mp.Process(target=loop,
                       args=(logger, self.is_running, pipe_out, pipe_in, self.height, self.width, self.__record_timer),
                       daemon=True)
        p.start()
        processes_threads.append(p)

    def stop(self):
        logger.debug("stopping Video Capture...")
        self.is_running.value = False


class Client:
    def __init__(self):
        logger.debug("Initializing Client Class...")
        # Network
        self.__ip = config.ip
        self.__port = config.port
        self.__identifier = b"c"  # camera
        self.__server_crashed = False
        self.__management_connection = self.__create_management_connection()
        self.__initialize_management_connection()
        self.__udp_connection = self.__create_udp_connection()
        # Camera
        self.__chunk_size = self.__request_chunk_size()
        logger.debug("chunk size set.")
        self.__resolution = (config.custom_frame_height, config.custom_frame_width) \
            if config.use_custom_resolution else self.__request_resolution()
        self.__update_server_resolution_if_necessary(self.__resolution)
        self.__capture = Capture(self.__resolution)
        logger.debug("resolution set.")
        logger.debug("Client Class initialized.")

    def __create_management_connection(self):
        logger.debug("Creating management connection...")
        while not self.__server_crashed:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((self.__ip, self.__port))
            if result == 0:
                sock.setblocking(True)
                logger.debug("Management connection created.")
                return sock
            sock.close()
            time.sleep(5)

    def __initialize_management_connection(self):
        logger.debug("Initialize management connection.")
        self.__management_connection.send(self.__identifier)

    def __create_udp_connection(self):
        logger.debug("creating udp connection...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, config.udp_send_buffer)
        logger.debug("udp connection created.")
        return sock

    def __request_chunk_size(self):
        logger.debug("requesting chunk size...")
        self.__management_connection.send(b"gc")  # get chunk_size
        return struct.unpack(">H", self.__management_connection.recv(struct.calcsize(">H")))[0]

    def __request_resolution(self):
        logger.debug("request server resolution...")
        self.__management_connection.send(b"gr")  # get resolution
        logger.debug("set resolution to server resolution.")
        resolution = struct.unpack(">2H", self.__management_connection.recv(struct.calcsize(">2H")))
        return resolution

    def __update_server_resolution_if_necessary(self, resolution):
        if config.use_custom_resolution:
            height, width = resolution
            self.__management_connection.send(b"sr")  # set resolution
            self.__management_connection.send(struct.pack(">2H", height, width))
            logger.debug("Send custom resolution to server.")

    def __listen_for_commands(self):
        logger.info("listening for commands...")
        logger.info("client started.")
        while True:
            command = self.__management_connection.recv(1)
            logger.debug(f"Command received: {command}")
            # Start stream
            if command == struct.pack(">?", True):
                self.__start_stream()
            # Stop Stream
            elif command == struct.pack(">?", False):
                self.__stop_stream()
                break
            # Server crashed
            elif command == b"":
                self.__handle_server_crash()
                if self.__server_crashed:
                    break
        logger.debug("stop listening for commands.")

    def __start_stream(self):
        logger.info("starting stream...")
        frame_pipe_out, frame_pipe_in = mp.Pipe(False)
        self.__capture.start(frame_pipe_in)
        self.__start_streaming_process(frame_pipe_out)
        logger.debug("stream started.")

    def __start_streaming_process(self, pipe_out):
        def loop(log, is_running, pipe, height, width, chunk_size, udp, ip, port, wait_chunk, wait_frame):
            log.info("streaming...")
            frame_byte_length = height * width * 3
            while is_running.value:
                frame = pipe.recv_bytes()
                for chunk_number in range(math.ceil(frame_byte_length / chunk_size)):
                    # print(chunk_number)
                    udp.sendto(struct.pack(">H", chunk_number) +
                               frame[chunk_size * chunk_number:chunk_size * (chunk_number + 1)], (ip, port))
                    time.sleep(wait_chunk)
                time.sleep(wait_frame)
            log.info("stream stopped.")

        p = mp.Process(target=loop, args=(logger, self.__capture.is_running, pipe_out, self.__capture.height,
                                          self.__capture.width, self.__chunk_size, self.__udp_connection, self.__ip,
                                          self.__port, config.wait_after_chunk, config.wait_after_frame), daemon=True)
        p.start()
        processes_threads.append(p)

    def __stop_stream(self):
        logger.info("stopping stream...")
        self.__capture.stop()
        join_all_processes_threads()

    def __handle_server_crash(self):
        logger.warning("Server crashed!")
        logger.info("Handling server crash...")
        self.__stop_stream()
        logger.debug("closing socket connections...")
        self.__management_connection.close()
        logger.debug("management connection closed.")
        self.__udp_connection.close()
        logger.debug("udp connection closed.")
        logger.debug("socket connections closed.")
        logger.debug(f"RetryAfterServerCrash: {config.retry_after_server_crash}")
        if config.retry_after_server_crash != 0:
            def signal_handler(signum, frame):
                logger.info("Server unreachable.")
                logger.info("closing client...")
                self.__server_crashed = True
            signal.signal(signal.SIGALRM, signal_handler)
            logger.info(f"trying to reach server for {config.retry_after_server_crash} seconds...")
            signal.alarm(config.retry_after_server_crash)
            self.__management_connection = self.__create_management_connection()
            signal.alarm(0)

            if not self.__server_crashed:
                logger.info("Server successfully reached.")
                logger.info("Server Crash handled.")
                logger.info("Restarting client...")
                self.__udp_connection = self.__create_udp_connection()
                self.__initialize_management_connection()
                self.__update_server_resolution_if_necessary(self.__resolution)
                self.__request_stream_start()
                logger.info("Client Successfully restarted.")
        else:
            logger.info("Server Crash handled.")
            logger.debug("closing client...")
            self.__server_crashed = True

    def run(self):
        logger.info("starting client...")
        self.__request_stream_start()
        self.__listen_for_commands()
        logger.info("client closed.")

    def __request_stream_start(self):
        logger.info("requesting stream start.")
        self.__management_connection.send(struct.pack(">?", True))


if __name__ == '__main__':
    client = Client()
    client.run()
    logger.info("-" * 10 + "APPLICATION STOPPED" + "-" * 10)
