import configparser
from src.shared.Logger import create_logger
import os
import sys
from src.shared.ConfigVerifier import ConfigVerifier
from datetime import datetime
import re


class Config:
    def __init__(self):
        server_config = configparser.ConfigParser()
        conf_path = os.path.join(os.path.join(os.path.dirname(os.path.dirname(sys.path[0])), "conf"), "server.ini")
        server_config.read(conf_path)
        # Developer Variables
        self.DebugMode = server_config["DEVELOPER"].getboolean("DebugMode")
        self.__logger = create_logger(__name__, self.DebugMode, "server.log")
        self.__logger.info(f"{'-'*25} STARTING RANDALL-V2.0 {'-'*25}")
        self.__logger.info("Loading Configuration file...")
        # Network Variables
        self.__logger.debug("Loading Network settings...")
        self.ServerIP = server_config["Network"]["ServerIP"]
        self.ServerPort = server_config["Network"].getint("ServerPort")
        self.ClientStoppingPoint = server_config["Network"]["ClientStoppingPoint"]
        self.__logger.debug("Network settings loaded.")
        # Video Variables
        self.__logger.debug("Loading Video settings...")
        self.DefaultHeight = server_config["Video"].getint("DefaultHeight")
        self.DefaultWidth = server_config["Video"].getint("DefaultWidth")
        self.FFMPEGOutputFileOptions = server_config["Video"]["FFMPEGOutputFileOptions"].strip()
        self.OutputFileExtension = server_config["Video"]["OutputFileExtension"]
        self.VideoCutTime = server_config["Video"]["VideoCutTime"]
        self.ConcatAmount = server_config["Video"].getint("ConcatAmount")
        self.__logger.debug("Video settings loaded.")
        # Storage Variables
        self.StoragePath = server_config["Storage"]["StoragePath"]
        self.FreeStorageAmountBeforeDeleting = server_config["Storage"].getint("FreeStorageAmountBeforeDeleting")
        # Process Variables
        self.__logger.debug("Loading Process settings...")
        self.ConsecutiveFFMPEGThreads = server_config["Processes"].getint("ConsecutiveFFMPEGThreads")
        self.__logger.debug("Process settings loaded.")
        # Webserver
        self.WebserverHost = server_config["Webserver"]["WebserverHost"]
        self.WebserverPort = server_config["Webserver"].getint("WebserverPort")
        self.WebserverTableWidth = server_config["Webserver"].getint("WebserverTableWidth")
        # Check Values
        self.__logger.debug("verifying settings...")
        self.__config_verifier = ConfigVerifier(self.__logger)
        self.__check_network_settings()
        self.__check_video_settings()
        self.__check_storage_settings()
        self.__check_process_settings()
        self.__check_webserver_settings()
        self.__logger.debug("settings verified.")
        self.__logger.info("Configuration file loaded.")

    def __check_network_settings(self):
        self.__config_verifier.check_ip_address(self.ServerIP)
        self.__config_verifier.check_port(self.ServerPort)

        self.__logger.debug("verifying ClientStoppingPoint.")
        match = re.match(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]", self.ClientStoppingPoint)
        if not match and self.ClientStoppingPoint != "None":
            self.__logger.error("Bad ClientStoppingPoint value in config. "
                                "Value must be a Time between: 00:00:00-23:59:59 or None.")
            raise Exception("BAD CLIENT STOPPING VALUE")
        self.ClientStoppingPoint = match.group(0) if match else None

    def __check_video_settings(self):
        self.__config_verifier.check_frame_height(self.DefaultHeight)
        self.__config_verifier.check_frame_width(self.DefaultWidth)

        self.__logger.debug("verifying VideoCutTime.")
        if self.VideoCutTime == "None":
            self.VideoCutTime = None
        else:
            if self.VideoCutTime == "00:00:00":
                raise Exception("BAD VIDEO CUT TIME VALUE")
            try:
                datetime.strptime(self.VideoCutTime, "%H:%M:%S")
            except ValueError:
                self.__logger.error("Bad VideoCutTime value in config. Max Value: 23:59:59 OR None")
                raise Exception("BAD VIDEO CUT TIME VALUE")
            else:
                self.VideoCutTime = datetime.strptime(self.VideoCutTime, "%H:%M:%S")

        self.__logger.debug("verifying FFMPEGOutputFileOptions.")
        if "&&" in self.FFMPEGOutputFileOptions:
            self.__logger.error("FFMPEG options can not contain '&&'.")
            raise Exception("BAD FFMPEG OUTPUT FILE OPTIONS")

        self.__logger.debug("verifying ConcatAmount.")
        if self.ConcatAmount < 1:
            self.__logger.debug("Bad ConcatAmount value. Value can not be negative or 0.")
            raise Exception("BAD CONCAT AMOUNT")

    def __check_storage_settings(self):
        self.__logger.debug("verifying StoragePath.")
        if not os.path.isdir(self.StoragePath):
            self.__logger.debug("Bad StoragePath value. Directory doesn't exist.")
            raise Exception("BAD STORAGE PATH")

        self.__logger.debug("verifying FreeStorageAmountBeforeDeleting.")
        if self.FreeStorageAmountBeforeDeleting <= 0:
            self.__logger.debug("Bad FreeStorageAmountBeforeDeleting value. Value Can not be negative or zero")
            raise Exception("BAD FREE STORAGE AMOUNT BEFORE DELETING")

    def __check_process_settings(self):
        self.__logger.debug("verifying ConsecutiveFFMPEGThreads.")
        if self.ConsecutiveFFMPEGThreads <= 0:
            self.__logger.debug("Bad ConsecutiveFFMPEGThreads value. The value cannot be negative or 0.")
            raise Exception("BAD CONSECUTIVE FFMPEG THREADS VALUE")

    def __check_webserver_settings(self):
        self.__config_verifier.check_ip_address(self.WebserverHost)
        self.__config_verifier.check_port(self.WebserverPort)

        self.__logger.debug("verifying WebserverTableWidth.")
        if self.WebserverTableWidth < 1:
            self.__logger.debug("Bad WebserverTableWidth value. The The value cannot be negative or 0.")
            raise Exception("BAD WEBSERVER TABLE WIDTH")


config = Config()
