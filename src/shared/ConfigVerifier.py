import socket


class ConfigVerifier:
    def __init__(self, logger):
        self.__logger = logger

    def check_ip_address(self, ip):
        self.__logger.debug("verifying ServerIP.")
        try:
            socket.inet_aton(ip)
        except socket.error:
            self.__logger.exception("Bad IP Address detected in config.")
            raise Exception("BAD IP ADDRESS")

    def check_port(self, port):
        self.__logger.debug("verifying ServerPort.")
        if port > 65535 or port < 1:
            self.__logger.error("Bad Port detected in config. %s", "Allowed ports: 1 < port < 65535")
            raise Exception("BAD PORT")

    def check_frame_height(self, height):
        self.__logger.debug("verifying FrameHeight.")
        if height < 0:
            self.__logger.error("Bad frame height. %s", "Value can not be negative.")
            raise Exception("BAD FRAME HEIGHT")

    def check_frame_width(self, width):
        self.__logger.debug("verifying FrameWidth.")
        if width < 0:
            self.__logger.error("Bad frame width. %s", "Value can not be negative.")
            raise Exception("BAD FRAME WIDTH")
