from src.shared.Logger import create_logger
from src.shared.ConfigVerifier import ConfigVerifier
import configparser
import cv2
import sys
import os


class Config:
    def __init__(self):
        client_config = configparser.ConfigParser()
        conf_path = os.path.join(os.path.join(os.path.dirname(os.path.dirname(sys.path[0])), "conf"), "client.ini")
        client_config.read(conf_path)
        # Developer Variables
        self.DebugMode = client_config["DEVELOPER"].getboolean("DebugMode")
        self.__logger = create_logger(__name__, self.DebugMode, "client.log")
        self.__logger.info("Loading Configuration file...")
        # Network Variables
        self.__logger.debug("Loading Network settings...")
        self.ServerIP = client_config["Network"]["ServerIP"]
        self.ServerPort = client_config["Network"].getint("ServerPort")
        self.WaitAfterFrame = client_config["Network"].getfloat("WaitAfterFrame")
        self.RetryAfterServerCrash = client_config["Network"].getint("RetryAfterServerCrash")
        self.__logger.debug("Network settings loaded.")
        # Camera Variables
        self.__logger.debug("Loading Camera settings...")
        self.CaptureDevice = client_config["VideoCapture"].getint("CaptureDevice")
        self.UseCustomResolution = client_config["VideoCapture"].getboolean("UseCustomResolution")
        self.__log_custom_resolution_mode()
        self.CustomFrameHeight = client_config["VideoCapture"].getint("CustomFrameHeight")
        self.CustomFrameWidth = client_config["VideoCapture"].getint("CustomFrameWidth")
        self.__logger.debug("Camera settings loaded.")
        # Check Values
        self.__logger.debug("verifying settings...")
        self.__config_verifier = ConfigVerifier(self.__logger)
        self.__check_network_settings()
        self.__check_video_capture_settings()
        self.__logger.debug("settings verified.")
        self.__logger.info("Configuration file loaded.")

    def __log_custom_resolution_mode(self):
        if self.UseCustomResolution:
            self.__logger.debug("use custom resolution: enabled")
        else:
            self.__logger.debug("use custom resolution: disabled")

    def __check_network_settings(self):
        self.__config_verifier.check_ip_address(self.ServerIP)
        self.__config_verifier.check_port(self.ServerPort)

        self.__logger.debug("verifying WaitAfterFrame.")
        if self.WaitAfterFrame < 0:
            self.__logger.error("Bad WaitAfterFrame value in config. %s", "Value can not be negative.")
            raise Exception("BAD WAIT VALUE")

        self.__logger.debug("verifying RetryAfterCrash")
        if self.RetryAfterServerCrash < 0:
            self.__logger.error("Bad RetryAfterCrash value in config. %s", "Value can not be negative.")
            raise Exception("BAD CRASH WAIT VALUE")

    def __check_video_capture_settings(self):
        self.__logger.debug("verifying CaptureDevice.")
        self.__check_capture_device()

        if self.UseCustomResolution:
            self.__config_verifier.check_frame_height(self.CustomFrameHeight)
            self.__config_verifier.check_frame_width(self.CustomFrameWidth)

    def __check_capture_device(self):
        if self.CaptureDevice < 0:
            self.__logger.error("Bad CaptureDevice value. %s", "Value can not be negative.")
            raise Exception("BAD CAPTURE DEVICE")

        cap = cv2.VideoCapture(self.CaptureDevice)
        if cap.isOpened():
            cap.release()
        else:
            self.__logger.error("Capture Device failed to initialize.")
            sys.exit(1)


config = Config()
