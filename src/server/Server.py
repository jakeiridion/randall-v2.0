import sys
import time

from src.shared.Logger import create_logger
from Config import config
import multiprocessing as mp
import ctypes
import socket
from threading import Thread
import struct
# Delete Me
import numpy as np
import cv2


class Server:
    def __init__(self):
        self.__logger = create_logger(__name__, config.debug_mode, "server.log")
        self.__logger.debug("[Server]: Initializing Server Class...")
        # Processes
        self.__management_connections = {}
        self.__stream_connections = {}
        self.__camera_processes = {}
        self.__server_processes_threads = []
        # Variables
        self.__is_running = mp.Value(ctypes.c_bool, True)
        self.__height = 320
        self.__width = 480
        self.__ip = "192.168.3.6"
        self.__port = 5050
        # Network
        self.__tcp_sock = self.__create_tcp_socket()
        # Start Network listening
        self.__start_handling_new_connections_thread()
        self.__logger.debug("[Server]: Server Class Initialized.")
        # Delete me
        self.test = None

    def __create_tcp_socket(self):
        self.__logger.debug("[Server]: creating tcp socket...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        sock.setblocking(True)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 7456540)
        sock.bind((self.__ip, self.__port))
        self.__logger.debug("[Server]: tcp socket created.")
        return sock

    def __start_handling_new_connections_thread(self):
        self.__logger.debug("[Server]: listening for connections....")
        self.__tcp_sock.listen()

        def loop(is_running, tcp, log):
            while is_running.value:
                conn, addr = tcp.accept()
                log.debug(f"[Server]: client {addr[0]} connected to server.")
                identifier = conn.recv(1)
                log.debug(f"[Server]: identifier received: '{identifier.decode('utf-8')}' from client: {addr[0]}")
                self.__handle_identifier(identifier, conn, addr[0])

        t = Thread(target=loop, args=[self.__is_running, self.__tcp_sock, self.__logger], daemon=True)
        t.start()
        self.__server_processes_threads.append(t)

    def __handle_identifier(self, identifier, conn, ip):
        self.__logger.debug(f"[Server]: handling identifier '{identifier.decode('utf-8')}'...")
        # management
        if identifier == b"m":
            self.__logger.debug(f"[{ip}]: management connection created.")
            self.__logger.debug("[Server]: processing new management connection...")
            self.__management_connections[ip] = conn
            self.__handle_management_connection(conn, ip)
        # camera
        elif identifier == b"c" and self.__management_connections.get(ip) is not None:
            self.__logger.debug(f"[{ip}]: camera connection created.")
            self.__logger.debug("[Server]: processing new camera connection...")
            self.__stream_connections[ip] = conn
        else:
            self.__logger.debug(f"[Server]: dropping identifier {identifier.decode('utf-8')}...")
            conn.close()
            self.__logger.debug("[Server]: connection dropped.")
        self.__logger.debug("[Server]: identifier handled.")

    def __handle_management_connection(self, connection, ip_address):
        def loop(log, conn, ip, height, width):
            log.debug(f"[{ip}]: handling management connection...")
            is_running = mp.Value(ctypes.c_bool, False)
            log.debug(f"[{ip}]: listening for commands...")
            while True:
                try:
                    request = conn.recv(2)
                except OSError:
                    break
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
                    height, width = ip, struct.unpack(">2H", conn.recv(struct.calcsize(">2H")))
                    log.debug(f"[{ip}]: custom resolution received.")
                # start stream
                elif request == struct.pack(">?", True):
                    log.debug(f"[{ip}]: requests stream start...")
                    self.__start_stream(log, is_running, height, width, ip, conn)

        t = Thread(target=loop, args=[self.__logger, connection, ip_address, self.__height, self.__width], daemon=True)
        t.start()
        self.__camera_processes[ip_address] = [t]

    def __start_stream(self, log, is_running, height, width, ip, conn):
        log.debug(f"[{ip}] starting stream...")
        is_running.value = True
        pipe_out, pipe_in = mp.Pipe(False)
        self.test = pipe_out
        self.__handle_stream_connection(is_running, pipe_in, height, width, ip, self.__stream_connections[ip])
        conn.send(struct.pack(">?", True))

    def __handle_stream_connection(self, is_running, pipe_in, height, width, ip_address, stream_connection):
        def loop(log, ip, conn, h, w, is_run, pipe):
            log.debug(f"[{ip}]: stream started.")
            frame_byte_size = h * w * 3
            while is_run.value:
                buffer = b""
                while len(buffer) < frame_byte_size:
                    buffer += conn.recv(frame_byte_size-len(buffer))
                pipe.send_bytes(buffer)
            log.debug(f"[{ip}]: stream stopped..")

        p = mp.Process(target=loop, args=(self.__logger, ip_address, stream_connection, height, width,
                                          is_running, pipe_in), daemon=True)
        p.start()
        self.__camera_processes[ip_address].append(p)

    def stop_all_streams(self):
        for key in self.__management_connections:
            self.__management_connections[key].send(struct.pack(">?", False))

    def restart_stream(self):
        for key in self.__management_connections:
            self.__management_connections[key].send(struct.pack(">?", True))

    def quit_all_clients(self):
        for key in self.__management_connections:
            self.__management_connections[key].send(b"q")
            self.__management_connections[key].close()
            self.__stream_connections[key].close()
            self.__join_all_processes_threads()
        self.__management_connections.clear()
        self.__stream_connections.clear()

    def __join_all_processes_threads(self):
        self.__logger.debug("joining processes/threads...")
        for key in self.__camera_processes:
            for item in self.__camera_processes[key]:
                self.__logger.debug(f"joining thread: {item}") if isinstance(type(item), type(Thread())) \
                    else self.__logger.debug(f"joining process: {item}")
                item.join()
                self.__logger.debug(f"thread joined: {item}") if isinstance(type(item), type(Thread())) \
                    else self.__logger.debug(f"process joined: {item}")
        self.__logger.debug("all threads/processes joined.")
        self.__camera_processes.clear()


if __name__ == '__main__':
    server = Server()
    while True:
        if server.test is None:
            continue
        buffer = server.test.recv_bytes()
        frame = np.reshape(np.frombuffer(buffer, dtype=np.uint8), (320, 480, 3))
        cv2.waitKey(1)
        cv2.imshow("frame", frame)
