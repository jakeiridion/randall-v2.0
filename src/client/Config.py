from src.shared.Logger import create_logger
import configparser
import socket
import cv2
import sys


class Config:
    def __init__(self):
        client_config = configparser.ConfigParser()
        client_config.read("conf/client.ini")
        # Default Variables
        self.debug_mode = client_config["DEVELOPER"].getboolean("DebugMode")
        self.__logger = create_logger(__name__, self.debug_mode, "logs/client.log")
        self.__logger.info("Loading Configuration file...")
        # Network Variables
        self.__logger.debug("Loading Network settings...")
        self.ip = client_config["Network"]["ServerIP"]
        self.port = client_config["Network"].getint("ServerPORT")
        self.udp_send_buffer = client_config["Network"].getint("UdpSendBuffer")
        self.wait_after_chunk = client_config["Network"].getfloat("WaitAfterChunk")
        self.wait_after_frame = client_config["Network"].getfloat("WaitAfterFrame")
        self.retry_after_server_crash = client_config["Network"].getint("RetryAfterServerCrash")
        self.__logger.debug("Network settings loaded.")
        # Camera Variables
        self.__logger.debug("Loading Camera settings...")
        self.capture_device = client_config["VideoCapture"].getint("CaptureDevice")
        self.use_custom_resolution = client_config["VideoCapture"].getboolean("UseCustomResolution")
        self.__log_custom_resolution_mode()
        self.custom_frame_height = client_config["VideoCapture"].getint("CustomFrameHeight")
        self.custom_frame_width = client_config["VideoCapture"].getint("CustomFrameWidth")
        self.__logger.debug("Camera settings loaded.")
        # Check Values
        self.__logger.debug("verifying settings...")
        self.__check_network_settings()
        self.__check_video_capture_settings()
        self.__logger.debug("settings verified.")
        self.__logger.info("Configuration file loaded.")

    def __log_custom_resolution_mode(self):
        if self.use_custom_resolution:
            self.__logger.debug("use custom resolution: enabled")
        else:
            self.__logger.debug("use custom resolution: disabled")

    def __check_network_settings(self):
        self.__logger.debug("verifying ServerIP.")
        try:
            socket.inet_aton(self.ip)
        except socket.error:
            self.__logger.exception("Bad IP Address detected in config.")
            raise Exception("BAD IP ADDRESS")

        self.__logger.debug("verifying ServerPORT.")
        if self.port > 65535 or self.port < 1:
            self.__logger.error("Bad Port detected in config. %s", "Allowed ports: 1 < port < 65535")
            raise Exception("BAD PORT")

        self.__logger.debug("verifying UdpSendBuffer.")
        if self.udp_send_buffer < 1:
            self.__logger.error("Bad udp receive value in config. %s", "Value can not be negative.")
            raise Exception("BAD UDP SEND BUFFER")

        self.__logger.debug("verifying WaitAfterChunk.")
        if self.wait_after_chunk < 0:
            self.__logger.error("Bad wait value in config. %s", "Value can not be negative.")
            raise Exception("BAD WAIT VALUE")

        self.__logger.debug("verifying WaitAfterFrame.")
        if self.wait_after_frame < 0:
            self.__logger.error("Bad wait value in config. %s", "Value can not be negative.")
            raise Exception("BAD WAIT VALUE")

        self.__logger.debug("verifying RetryAfterCrash")
        if self.retry_after_server_crash < 0:
            self.__logger.error("Bad crash wait value in config. %s", "Value can not be negative.")
            raise Exception("BAD CRASH WAIT VALUE")

    def __check_video_capture_settings(self):
        self.__logger.debug("verifying CaptureDevice.")
        self.__check_capture_device()

        if self.use_custom_resolution:
            self.__logger.debug("verifying CustomFrameHeight.")
            if self.custom_frame_height < 0:
                self.__logger.error("Bad frame height. %s", "Value can not be negative.")
                raise Exception("BAD FRAME HEIGHT")

            self.__logger.debug("verifying CustomFrameWidth.")
            if self.custom_frame_width < 0:
                self.__logger.error("Bad frame width. %s", "Value can not be negative.")
                raise Exception("BAD FRAME WIDTH")

    def __check_capture_device(self):
        if self.capture_device < 0:
            self.__logger.error("Bad capture device value. %s", "Value can not be negative.")
            raise Exception("BAD CAPTURE DEVICE")

        cap = cv2.VideoCapture(self.capture_device)
        if cap.isOpened():
            cap.release()
        else:
            self.__logger.error("Capture Device failed to initialize.")
            sys.exit(1)


config = Config()
