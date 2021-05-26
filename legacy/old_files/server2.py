import cv2
import numpy as np
from threading import Thread
import multiprocessing as mp
import struct
import socket
import logging
import configparser
import time


def initiate_logger():
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler("../client.log")
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
        self.__manager = mp.Manager()
        self.cameras = self.__manager.dict()
        self.threads_and_processes = {}

        # Variables
        self.__height = 480
        self.__width = 640

        self.__ip = "192.168.3.6"
        self.__port = 5050

        self.__chunk_size = 40000

        # Network
        self.__management_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__setup_management_connection()

        self.__udp_connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.__setup_udp_connection()
        self.__udp_buffer_out, self.__udp_buffer_in = mp.Pipe(False)

        self.__add_traffic_to_buffer()
        self.__add_traffic_to_chunk_queues()
        self.__handle_new_management_connections()

        logger.debug("[Server]: Server Class initialized.")

    def __setup_management_connection(self):
        logger.debug("[Server]: setting up management connection...")
        self.__management_connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        self.__management_connection.setblocking(True)
        logger.debug("[Server]: management connection set up.")

    def __setup_udp_connection(self):
        logger.debug("[Server]: setting up udp connection...")
        self.__udp_connection.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 7456540)
        self.__udp_connection.bind((self.__ip, self.__port))
        logger.debug("[Server]: udp connection set up.")

    def __handle_new_management_connections(self):
        logger.debug("[Server]: binding management connection...")
        self.__management_connection.bind((self.__ip, self.__port))
        logger.debug("[Server]: management connection bound.")
        logger.debug("[Server]: listening for connections....")
        self.__management_connection.listen()

        def loop():
            while True:
                conn, addr = self.__management_connection.accept()
                logger.debug(f"[Server]: client {addr[0]} connected to server.")
                identifier = conn.recv(1)
                logger.debug(f"[Server]: receiving identifier: '{identifier.decode('utf-8')}' from client: {addr[0]}")
                self.__handle_identifier(identifier, conn, addr[0])

        Thread(target=loop, daemon=True).start()

    def __handle_identifier(self, identifier, connection, ip):
        logger.debug(f"[Server]: handling identifier '{identifier.decode('utf-8')}'...")
        if identifier == b"c":  # camera
            logger.debug(f"[{ip}]: identified as camera.")
            logger.debug("[Server]: processing new camera...")
            # camera = [management connection, frame chunk pipe, frame pipe, frame height, frame width, is running]
            self.cameras[ip] = self.__manager.list(
                (connection, mp.Pipe(False), mp.Pipe(False), self.__height, self.__width, True))

            self.__handle_existing_management_connection(ip)
        else:
            logger.debug(f"[Server]: dropping unknown identifier {identifier.decode('utf-8')}...")
            connection.close()
            logger.debug("[Server]: connection dropped.")
        logger.debug("[Server]: identifier handled.")

    def __handle_existing_management_connection(self, ip):
        logger.debug(f"[{ip}]: handling management connection")

        def loop(camera):
            logger.debug(f"[{ip}]: listening for commands...")
            conn = camera[0]
            while True:
                request = conn.recv(2)
                logger.debug(f"[{ip}]: command received: '{request.decode('utf-8')}'")
                if request == b"gr":  # get resolution
                    logger.debug(f"[{ip}]: requesting frames resolution.")
                    logger.debug(f"[{ip}]: sending frame resolution to client...")
                    conn.send(struct.pack(">2H", self.__height, self.__width))
                    logger.debug(f"[{ip}]: resolution send.")
                elif request == b"sr":  # set resolution
                    logger.debug(f"[{ip}]: requests use of custom resolution")
                    logger.debug(f"[{ip}]: receiving custom resolution...")
                    resolution = struct.unpack(">2H", conn.recv(struct.calcsize(">2H")))
                    logger.debug(f"[{ip}]: custom resolution received.")
                    self.__set_custom_resolution(ip, resolution)
                elif request == b"gc":  # get chunk_size
                    logger.debug(f"[{ip}]: requests chunk size.")
                    logger.debug(f"[{ip}]: sending chunk size...")
                    conn.send(struct.pack(">H", self.__chunk_size))
                    logger.debug(f"[{ip}]: chunk size sent.")
                elif request == b"ex":  # exit
                    logger.debug(f"[{ip}]: requests camera shutdown.")
                    logger.debug(f"[{ip}]: handling camera shutdown...")
                    conn.close()
                    logger.debug(f"[{ip}]: management connection closed.")
                    del camera[ip]
                    logger.debug(f"[{ip}]: deleted from active camera list.")
                    logger.debug(f"[{ip}]: camera shutdown handled.")
                elif request == struct.pack(">?", True):  # start stream
                    logger.debug(f"[{ip}]: requests stream start...")
                    self.ready_stream(ip, camera)

        Thread(target=loop, args=(self.cameras[ip],), daemon=True).start()

    def __set_custom_resolution(self, ip, resolution):
        logger.debug(f"[{ip}]: setting new camera resolution...")
        height, width = resolution
        self.cameras[ip][3] = height
        self.cameras[ip][4] = width
        logger.debug(f"[{ip}]: custom resolution set.")

    def __add_traffic_to_buffer(self):
        logger.debug("[Server]: start listening on udp socket...")

        def loop(pipe):
            while True:
                chunk = self.__udp_connection.recvfrom(struct.calcsize(">H") + self.__chunk_size)
                pipe.send(chunk)

        mp.Process(target=loop, args=(self.__udp_buffer_in,), daemon=True).start()

    def __add_traffic_to_chunk_queues(self):
        logger.debug("[Server]: start udp buffer parsing...")

        def loop(cameras):
            while True:
                chunk, addr = self.__udp_buffer_out.recv()
                cameras[addr[0]][1][1].send_bytes(chunk)

        mp.Process(target=loop, args=(self.cameras,), daemon=True).start()

    def ready_stream(self, ip, camera):
        logger.debug(f"[{ip}]: starting stream...")
        camera[5] = True
        self.__handle_chunk_queue(ip)
        #self.__handle_frame_queue(ip)
        logger.debug(f"[{ip}]: accepting stream start...")
        camera[0].send(struct.pack(">?", True))
        logger.debug(f"[{ip}]: receiving frames...")

    def __handle_chunk_queue(self, ip):
        logger.debug(f"[{ip}]: assembling chunks...")

        def loop(camera):
            while camera[5]:
                buffer = b""
                t = []
                frame_byte_size = self.calculate_frame_byte_size(camera)
                number_of_iterations = int((frame_byte_size / self.__chunk_size) + 1)  # TODO: make sure it is odd
                chunk_number = 0
                while chunk_number < number_of_iterations:
                    data = camera[1][0].recv_bytes()
                    #print(len(data))
                    frame_count = struct.unpack(">H", data[:struct.calcsize(">H")])[0]
                    t.append(struct.unpack(">H", data[:struct.calcsize(">H")]))
                    buffer += b"\x00" * self.__calculate_chunks(frame_count, chunk_number) \
                              + data[struct.calcsize(">H"):] if frame_count >= chunk_number \
                        else b"\x00" * self.__calculate_chunks(number_of_iterations, chunk_number)
                    chunk_number = frame_count + 1 if frame_count >= chunk_number else number_of_iterations
                # The buffer is to large when the final chunk disappears and it is replaced with a full chunk of
                # darkness even tough the last bit of the frame doesnt have the same size as the inserted chunk.
                buffer = buffer[:frame_byte_size]
                # print(3*1280*720, len(buffer))
                print(t)
                print(len(t))
                #print(len(buffer))
                camera[2][1].send(self.__format_frame(buffer, camera))
            logger.debug("chunks assembled.")

        p = mp.Process(target=loop, args=(self.cameras[ip],), daemon=True)
        p.start()
        self.threads_and_processes[ip] = [p]

    def calculate_frame_byte_size(self, camera):
        return camera[3] * camera[4] * 3

    def __calculate_chunks(self, x, y):
        return self.__chunk_size * (x - y)

    def __format_frame(self, frame, camera):
        return np.reshape(np.frombuffer(frame, dtype=np.uint8),
                          (camera[3], camera[4], 3))

    def __handle_frame_queue(self, ip):
        pass


if __name__ == '__main__':
    server = Server()

    while True:
        if dict(server.cameras) == {}:
            continue
        frame = server.cameras["192.168.3.6"][2][0].recv()
        cv2.waitKey(1)
        cv2.imshow("frame", frame)

    #logger.info("-" * 10 + "APPLICATION STOPPED" + "-" * 10)
