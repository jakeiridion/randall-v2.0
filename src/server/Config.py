import configparser
from src.shared.Logger import create_logger
import os
import sys
from src.shared.ConfigVerifier import ConfigVerifier
from datetime import datetime


class Config:
    def __init__(self):
        server_config = configparser.ConfigParser()
        conf_path = os.path.join(os.path.join(os.path.dirname(os.path.dirname(sys.path[0])), "conf"), "server.ini")
        server_config.read(conf_path)
        # Developer Variables
        self.DebugMode = server_config["DEVELOPER"].getboolean("DebugMode")
        self.__logger = create_logger(__name__, self.DebugMode, "server.log")
        self.__logger.info("Loading Configuration file...")
        # Network Variables
        self.__logger.debug("Loading Network settings...")
        self.ServerIP = server_config["Network"]["ServerIP"]
        self.ServerPort = server_config["Network"].getint("ServerPort")
        self.__logger.debug("Network settings loaded.")
        # Video Variables
        self.__logger.debug("Loading Video settings...")
        self.DefaultHeight = server_config["Video"].getint("DefaultHeight")
        self.DefaultWidth = server_config["Video"].getint("DefaultWidth")
        self.VideoCutTime = server_config["Video"]["VideoCutTime"]
        self.FFMPEGOutputFileOptions = server_config["Video"]["FFMPEGOutputFileOptions"].strip()
        self.StoragePath = server_config["Video"]["StoragePath"]
        self.__logger.debug("Video settings loaded.")
        # Process Variables
        self.__logger.debug("Loading Process settings...")
        self.ConsecutiveFFMPEGThreads = server_config["Processes"].getint("ConsecutiveFFMPEGThreads")
        self.__logger.debug("Process settings loaded.")
        # Check Values
        self.__logger.debug("verifying settings...")
        self.__config_verifier = ConfigVerifier(self.__logger)
        self.__check_network_settings()
        self.__check_video_settings()
        self.__check_process_settings()
        self.__logger.debug("settings verified.")
        self.__logger.info("Configuration file loaded.")

    def __check_network_settings(self):
        self.__config_verifier.check_ip_address(self.ServerIP)
        self.__config_verifier.check_port(self.ServerPort)

    def __check_video_settings(self):
        self.__config_verifier.check_frame_height(self.DefaultHeight)
        self.__config_verifier.check_frame_width(self.DefaultWidth)

        self.__logger.debug("verifying VideoCutTime.")
        if self.VideoCutTime == "00:00:00":
            raise Exception("BAD VIDEO CUT TIME VALUE")
        try:
            datetime.strptime(self.VideoCutTime, "%H:%M:%S")
        except ValueError:
            self.__logger.error("Bad VideoCutTime value in config. Max Value: 23:59:59")
            raise Exception("BAD VIDEO CUT TIME VALUE")
        else:
            self.VideoCutTime = datetime.strptime(self.VideoCutTime, "%H:%M:%S")

        self.__logger.debug("verifying FFMPEGOutputFileOptions.")
        if "&&" in self.FFMPEGOutputFileOptions:
            self.__logger.error("FFMPEG options can not contain '&&'.")
            raise Exception("BAD FFMPEG OUTPUT FILE OPTIONS")

        self.__logger.debug("verifying StoragePath.")
        if not os.path.isdir(self.StoragePath):
            self.__logger.debug("Bad StoragePath value. Directory doesn't exist.")
            raise Exception("BAD STORAGE PATH")

    def __check_process_settings(self):
        self.__logger.debug("verifying ConsecutiveFFMPEGThreads.")
        if self.ConsecutiveFFMPEGThreads <= 0:
            self.__logger.debug("Bad ConsecutiveFFMPEGThreads value. The value cannot be negative or 0.")
            raise Exception("BAD CONSECUTIVE FFMPEG THREADS VALUE")


config = Config()
