import configparser
from src.shared.Logger import create_logger
import os


class Config:
    def __init__(self):
        conf_path = os.path.join(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "conf"),
                                 "server.ini")
        client_config = configparser.ConfigParser()
        client_config.read(conf_path)
        # Default Variables
        self.debug_mode = client_config["DEVELOPER"].getboolean("DebugMode")
        self.__logger = create_logger(__name__, self.debug_mode, "server.log")


config = Config()
