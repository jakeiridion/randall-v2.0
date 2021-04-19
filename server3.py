import cv2
import numpy as np
from threading import Thread
import multiprocessing as mp
import struct
import socket
import logging
import configparser
import time
import ctypes


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


class Config:
    def __init__(self):
        client_config = configparser.ConfigParser()
        client_config.read("server.ini")
        # Default Variables
        self.debug_mode = client_config["DEVELOPER"].getboolean("DebugMode")
        self.__handle_debug_mode()

    def __handle_debug_mode(self):
        if self.debug_mode:
            global logger
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter("%(asctime)s:%(name)s:%(levelname)s:%(message)s", datefmt="%Y-%m-%d %H:%M:%S")
            stream_handler.setFormatter(formatter)
            logger.addHandler(stream_handler)
            logger.info("-" * 10 + "APPLICATION STARTED" + "-" * 10)
            logger.debug("[Server]: DEBUG MODE ACTIVATED")


config = Config()


class Server:
    def __init__(self):
        logger.debug("[Server]: Initializing Server Class...")
        # Processes
        self.__cameras = mp.Manager().dict()
        self.__camera_processes = {}
        self.__server_processes_threads = []
        # Variables
        self.__is_running = mp.Value(ctypes.c_bool, True)
        self.__height = 480
        self.__width = 640
        self.__ip = "192.168.3.6"
        self.__port = 5050
        self.__chunk_size = 30000
        # Network
        self.__management_connection = self.__create_management_connection()
        self.__udp_connection = self.__create_udp_connection()
        self.__udp_buffer_out, self.__udp_buffer_in = mp.Pipe(False)
        # Start Network listening
        self.__start_udp_listener_process()
        self.__start_udp_chunk_sorting_process()
        self.__start_handling_new_connections_thread()
        logger.debug("[Server]: Server Class Initialized.")

    def __create_management_connection(self):
        logger.debug("[Server]: creating management socket...")
        mc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        mc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        mc.setblocking(True)
        mc.bind((self.__ip, self.__port))
        logger.debug("[Server]: management socket created.")
        return mc

    def __create_udp_connection(self):
        logger.debug("[Server]: creating udp socket...")
        uc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        uc.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 7456540)
        uc.bind((self.__ip, self.__port))
        logger.debug("[Server]: udp socket created.")
        return uc

    def __start_udp_listener_process(self):
        def loop(log, is_running, udp, pipe_in):
            log.debug("[Server]: starting to listen on udp socket...")
            while is_running.value:
                chunk = udp.recvfrom(struct.calcsize(">H") + self.__chunk_size)
                pipe_in.send(chunk)
            log.debug("[Server]: stopped listening on udp socket.")

        p = mp.Process(target=loop,
                       args=(logger, self.__is_running, self.__udp_connection, self.__udp_buffer_in), daemon=True)
        p.start()
        self.__server_processes_threads.append(p)

    def __start_udp_chunk_sorting_process(self):
        def loop(log, is_running, pipe_out, cameras):
            log.debug("[Server]: start udp buffer parsing...")
            while is_running.value:
                chunk, addr = pipe_out.recv()
                #print(cameras[addr[0]])
                cameras[addr[0]].send_bytes(chunk)

        p = mp.Process(target=loop, args=(logger, self.__is_running, self.__udp_buffer_out, self.__cameras), daemon=True)
        p.start()
        self.__server_processes_threads.append(p)

    def __start_handling_new_connections_thread(self):
        logger.debug("[Server]: listening for connections....")
        self.__management_connection.listen()

        def loop(is_running, tcp, log):
            while is_running.value:
                conn, addr = tcp.accept()
                log.debug(f"[Server]: client {addr[0]} connected to server.")
                identifier = conn.recv(1)
                log.debug(f"[Server]: identifier received: '{identifier.decode('utf-8')}' from client: {addr[0]}")
                self.__handle_identifier(identifier, conn, addr[0])

        t = Thread(target=loop, args=[self.__is_running, self.__management_connection, logger], daemon=True)
        t.start()
        self.__server_processes_threads.append(t)

    def __handle_identifier(self, identifier, conn, ip):
        logger.debug(f"[Server]: handling identifier '{identifier.decode('utf-8')}'...")
        if identifier == b"c":  # camera
            logger.debug(f"[{ip}]: identified as camera.")
            logger.debug("[Server]: processing new camera...")
            self.__start_handling_existing_connections_thread(conn, ip)
        else:
            logger.debug(f"[Server]: dropping unknown identifier {identifier.decode('utf-8')}...")
            conn.close()
            logger.debug("[Server]: connection dropped.")
        logger.debug("[Server]: identifier handled.")

    def __start_handling_existing_connections_thread(self, connection, ip_address):
        def loop(log, ip, conn, cameras):
            log.debug(f"[{ip}]: handling management connection...")
            is_running = mp.Value(ctypes.c_bool, False)
            height = self.__height
            width = self.__width
            log.debug(f"[{ip}]: listening for commands...")
            while True:
                request = conn.recv(2)
                log.debug(f"[{ip}]: command received: '{request.decode('utf-8')}'")
                # get Resolution
                if request == b"gr":
                    log.debug(f"[{ip}]: requesting frames resolution.")
                    log.debug(f"[{ip}]: sending frame resolution to client...")
                    conn.send(struct.pack(">2H", height, width))
                    log.debug(f"[{ip}]: resolution send.")
                # set resolution
                elif request == b"sr":
                    log.debug(f"[{ip}]: requests use of custom resolution")
                    log.debug(f"[{ip}]: receiving custom resolution...")
                    height, width = struct.unpack(">2H", conn.recv(struct.calcsize(">2H")))
                    log.debug(f"[{ip}]: custom resolution received.")
                # get chunk_size
                elif request == b"gc":
                    log.debug(f"[{ip}]: requests chunk size.")
                    log.debug(f"[{ip}]: sending chunk size...")
                    conn.send(struct.pack(">H", self.__chunk_size))
                    log.debug(f"[{ip}]: chunk size sent.")
                # start stream
                elif request == struct.pack(">?", True):
                    log.debug(f"[{ip}]: requests stream start...")
                    self.__start_stream(conn, ip, is_running, height, width)

        t = Thread(target=loop, args=[logger, ip_address, connection, self.__cameras], daemon=True)
        t.start()
        self.__server_processes_threads.append(t)

    def __start_stream(self, conn, ip, is_running, height, width):
        logger.debug(f"[{ip}]: starting stream...")
        # Creating shared values
        is_running.value = True
        chunk_pipe_out, chunk_pipe_in = mp.Pipe(False)
        frame_pipe_out, frame_pipe_in = mp.Pipe(False)
        self.__cameras[ip] = chunk_pipe_in
        # Start camera chunk/frame processing processes:
        self.__start_chunk_processing_process(is_running, height, width, chunk_pipe_out, frame_pipe_in, ip)

        logger.debug(f"[{ip}]: accepting stream start...")
        conn.send(struct.pack(">?", True))
        logger.debug(f"[{ip}]: receiving frames...")

    def __start_chunk_processing_process(self, is_running, height, width, pipe_out, pipe_in, ip):
        def loop(pipe):
            while True:
                x = pipe.recv_bytes()
                print(struct.unpack(">H", x[:struct.calcsize(">H")])[0])
        mp.Process(target=loop, args=(pipe_out,), daemon=True).start()


if __name__ == '__main__':
    server = Server()
    while True:
        pass

