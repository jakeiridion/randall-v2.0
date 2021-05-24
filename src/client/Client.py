from src.shared.Logger import create_logger
from Config import config
from Capture import Capture
import socket
import time
import struct
import multiprocessing as mp
import signal
from threading import Thread


class Client:
    def __init__(self):
        self.__logger = create_logger(__name__, config.debug_mode, "logs/client.log")
        self.__logger.debug("Initializing Client Class...")
        self.__processes_threads = []
        # Network
        self.__ip = config.ip
        self.__port = config.port
        self.__server_crashed = False
        self.__management_connection = self.__create_connection()
        self.__stream_connection = self.__create_connection()
        self.__initialize_connections()
        # Camera
        self.__chunk_size = self.__request_chunk_size()
        self.__logger.debug("chunk size set.")
        self.__resolution = (config.custom_frame_height, config.custom_frame_width) \
            if config.use_custom_resolution else self.__request_resolution()
        self.__update_server_resolution_if_necessary()
        self.__capture = Capture(self.__resolution)
        self.__logger.debug("resolution set.")
        self.__logger.debug("Client Class initialized.")

    def __create_connection(self):
        self.__logger.debug("Creating connection...")
        while not self.__server_crashed:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((self.__ip, self.__port))
            if result == 0:
                sock.setblocking(True)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, config.stream_send_buffer)
                self.__logger.debug("connection created.")
                return sock
            sock.close()
            time.sleep(5)

    def __initialize_connections(self):
        self.__logger.debug("Initialize management connection.")
        self.__management_connection.send(b"m")  # management
        self.__logger.debug("Initialize stream connection.")
        self.__stream_connection.send(b"c")  # camera

    def __request_chunk_size(self):
        self.__logger.debug("requesting chunk size...")
        self.__management_connection.send(b"gc")  # get chunk_size
        return struct.unpack(">H", self.__management_connection.recv(struct.calcsize(">H")))[0]

    def __request_resolution(self):
        self.__logger.debug("request server resolution...")
        self.__management_connection.send(b"gr")  # get resolution
        self.__logger.debug("set resolution to server resolution.")
        resolution = struct.unpack(">2H", self.__management_connection.recv(struct.calcsize(">2H")))
        return resolution

    def __update_server_resolution_if_necessary(self):
        if config.use_custom_resolution:
            height, width = self.__resolution
            self.__management_connection.send(b"sr")  # set resolution
            self.__management_connection.send(struct.pack(">2H", height, width))
            self.__logger.debug("Send custom resolution to server.")

    def run(self):
        self.__logger.info("starting client...")
        self.__listen_for_commands()
        self.__logger.info("client closed.")

    def __listen_for_commands(self):
        self.__logger.info("listening for commands...")
        self.__logger.info("client started.")
        while True:
            command = self.__management_connection.recv(1)
            self.__logger.debug(f"Command received: {command}")
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
        self.__logger.debug("stop listening for commands.")

    def __start_stream(self):
        self.__logger.info("starting stream...")
        frame_pipe_out, frame_pipe_in = mp.Pipe(False)
        self.__capture.start(frame_pipe_in)
        self.__start_streaming_process(frame_pipe_out)
        self.__logger.debug("stream started.")

    def __start_streaming_process(self, pipe_out):
        def loop(log, is_running, pipe, conn, wait_frame):
            log.info("streaming...")
            while is_running.value:
                frame = pipe.recv_bytes()
                conn.sendall(frame)
                time.sleep(wait_frame)
            log.info("stream stopped.")
        p = mp.Process(target=loop, args=(self.__logger, self.__capture.is_running, pipe_out, self.__stream_connection,
                                          config.wait_after_frame), daemon=True)
        p.start()
        self.__processes_threads.append(p)

    def __stop_stream(self):
        self.__logger.info("stopping stream...")
        self.__capture.stop()
        self.__join_all_processes_threads()

    def __join_all_processes_threads(self):
        self.__processes_threads += self.__capture.get_processes_threads()
        self.__logger.debug("joining processes/threads...")
        for item in self.__processes_threads:
            self.__logger.debug(f"joining thread: {item}") if isinstance(type(item), type(Thread())) \
                else self.__logger.debug(f"joining process: {item}")
            item.join()
            self.__logger.debug(f"thread joined: {item}") if isinstance(type(item), type(Thread())) \
                else self.__logger.debug(f"process joined: {item}")
        self.__logger.debug("all threads/processes joined.")
        self.__processes_threads.clear()

    def __handle_server_crash(self):
        self.__logger.warning("Server crashed!")
        self.__logger.info("Handling server crash...")
        self.__stop_stream()
        self.__logger.debug("closing socket connections...")
        self.__management_connection.close()
        self.__logger.debug("management connection closed.")
        self.__stream_connection.close()
        self.__logger.debug("stream connection closed.")
        self.__logger.debug("socket connections closed.")
        self.__logger.debug(f"RetryAfterServerCrash: {config.retry_after_server_crash}")
        if config.retry_after_server_crash != 0:
            def signal_handler(signum, frame):
                signum.__logger.info("Server unreachable.")
                signum.__logger.info("closing client...")
                self.__server_crashed = True

            signal.signal(signal.SIGALRM, signal_handler)
            self.__logger.info(f"trying to reach server for {config.retry_after_server_crash} seconds...")
            signal.alarm(config.retry_after_server_crash)
            self.__management_connection = self.__create_connection()
            self.__stream_connection = self.__create_connection()
            signal.alarm(0)

            if not self.__server_crashed:
                self.__logger.info("Server successfully reached.")
                self.__logger.info("Server Crash handled.")
                self.__logger.info("Restarting client...")
                self.__initialize_connections()
                self.__update_server_resolution_if_necessary()
                self.__logger.info("Client Successfully restarted.")
        else:
            self.__logger.info("Server Crash handled.")
            self.__logger.debug("closing client...")
            self.__server_crashed = True


if __name__ == '__main__':
    client = Client()
    client.run()
