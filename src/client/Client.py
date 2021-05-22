from src.shared.Logger import create_logger
from Config import config
from Capture import Capture
import socket
import time
import struct
import multiprocessing as mp
import math
import signal
from threading import Thread


# TODO: reclassify logging levels
class Client:
    def __init__(self):
        self.logger = create_logger(__name__, config.debug_mode, "logs/client.log")
        self.logger.debug("Initializing Client Class...")
        self.__processes_threads = []
        # Network
        self.__ip = config.ip
        self.__port = config.port
        self.__identifier = b"c"  # camera
        self.__server_crashed = False
        self.__management_connection = self.__create_management_connection()
        self.__initialize_management_connection()
        self.__udp_connection = self.__create_udp_connection()
        # Camera
        self.__chunk_size = self.__request_chunk_size()
        self.logger.debug("chunk size set.")
        self.__resolution = (config.custom_frame_height, config.custom_frame_width) \
            if config.use_custom_resolution else self.__request_resolution()
        self.__update_server_resolution_if_necessary(self.__resolution)
        self.__capture = Capture(self.__resolution)
        self.logger.debug("resolution set.")
        self.logger.debug("Client Class initialized.")

    def __create_management_connection(self):
        self.logger.debug("Creating management connection...")
        while not self.__server_crashed:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((self.__ip, self.__port))
            if result == 0:
                sock.setblocking(True)
                self.logger.debug("Management connection created.")
                return sock
            sock.close()
            time.sleep(5)

    def __initialize_management_connection(self):
        self.logger.debug("Initialize management connection.")
        self.__management_connection.send(self.__identifier)

    def __create_udp_connection(self):
        self.logger.debug("creating udp connection...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, config.udp_send_buffer)
        self.logger.debug("udp connection created.")
        return sock

    def __request_chunk_size(self):
        self.logger.debug("requesting chunk size...")
        self.__management_connection.send(b"gc")  # get chunk_size
        return struct.unpack(">H", self.__management_connection.recv(struct.calcsize(">H")))[0]

    def __request_resolution(self):
        self.logger.debug("request server resolution...")
        self.__management_connection.send(b"gr")  # get resolution
        self.logger.debug("set resolution to server resolution.")
        resolution = struct.unpack(">2H", self.__management_connection.recv(struct.calcsize(">2H")))
        return resolution

    def __update_server_resolution_if_necessary(self, resolution):
        if config.use_custom_resolution:
            height, width = resolution
            self.__management_connection.send(b"sr")  # set resolution
            self.__management_connection.send(struct.pack(">2H", height, width))
            self.logger.debug("Send custom resolution to server.")

    def __listen_for_commands(self):
        self.logger.info("listening for commands...")
        self.logger.info("client started.")
        while True:
            command = self.__management_connection.recv(1)
            self.logger.debug(f"Command received: {command}")
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
        self.logger.debug("stop listening for commands.")

    def __start_stream(self):
        self.logger.info("starting stream...")
        frame_pipe_out, frame_pipe_in = mp.Pipe(False)
        self.__capture.start(frame_pipe_in)
        self.__start_streaming_process(frame_pipe_out)
        self.logger.debug("stream started.")

    def __start_streaming_process(self, pipe_out):
        def loop(log, is_running, pipe, height, width, chunk_size, udp, ip, port, wait_chunk, wait_frame):
            log.info("streaming...")
            frame_byte_length = height * width * 3
            while is_running.value:
                frame = pipe.recv_bytes()
                for chunk_number in range(math.ceil(frame_byte_length / chunk_size)):
                    # print(chunk_number)
                    udp.sendto(struct.pack(">H", chunk_number) +
                               frame[chunk_size * chunk_number:chunk_size * (chunk_number + 1)], (ip, port))
                    time.sleep(wait_chunk)
                time.sleep(wait_frame)
            log.info("stream stopped.")

        p = mp.Process(target=loop, args=(self.logger, self.__capture.is_running, pipe_out, self.__capture.height,
                                          self.__capture.width, self.__chunk_size, self.__udp_connection, self.__ip,
                                          self.__port, config.wait_after_chunk, config.wait_after_frame), daemon=True)
        p.start()
        self.__processes_threads.append(p)

    def __stop_stream(self):
        self.logger.info("stopping stream...")
        self.__capture.stop()
        self.__join_all_processes_threads()

    def __join_all_processes_threads(self):
        self.__processes_threads += self.__capture.get_processes_threads()
        self.logger.debug("joining processes/threads...")
        for item in self.__processes_threads:
            self.logger.debug(f"joining thread: {item}") if isinstance(type(item), type(Thread()))  \
                else self.logger.debug(f"joining process: {item}")
            item.join()
            self.logger.debug(f"thread joined: {item}") if isinstance(type(item), type(Thread())) \
                else self.logger.debug(f"process joined: {item}")
        self.logger.debug("all threads/processes joined.")
        self.__processes_threads.clear()

    def __handle_server_crash(self):
        self.logger.warning("Server crashed!")
        self.logger.info("Handling server crash...")
        self.__stop_stream()
        self.logger.debug("closing socket connections...")
        self.__management_connection.close()
        self.logger.debug("management connection closed.")
        self.__udp_connection.close()
        self.logger.debug("udp connection closed.")
        self.logger.debug("socket connections closed.")
        self.logger.debug(f"RetryAfterServerCrash: {config.retry_after_server_crash}")
        if config.retry_after_server_crash != 0:
            def signal_handler(signum, frame):
                signum.logger.info("Server unreachable.")
                signum.logger.info("closing client...")
                self.__server_crashed = True
            signal.signal(signal.SIGALRM, signal_handler)
            self.logger.info(f"trying to reach server for {config.retry_after_server_crash} seconds...")
            signal.alarm(config.retry_after_server_crash)
            self.__management_connection = self.__create_management_connection()
            signal.alarm(0)

            if not self.__server_crashed:
                self.logger.info("Server successfully reached.")
                self.logger.info("Server Crash handled.")
                self.logger.info("Restarting client...")
                self.__udp_connection = self.__create_udp_connection()
                self.__initialize_management_connection()
                self.__update_server_resolution_if_necessary(self.__resolution)
                self.__request_stream_start()
                self.logger.info("Client Successfully restarted.")
        else:
            self.logger.info("Server Crash handled.")
            self.logger.debug("closing client...")
            self.__server_crashed = True

    def run(self):
        self.logger.info("starting client...")
        self.__request_stream_start()
        self.__listen_for_commands()
        self.logger.info("client closed.")

    def __request_stream_start(self):
        self.logger.info("requesting stream start.")
        self.__management_connection.send(struct.pack(">?", True))


if __name__ == '__main__':
    client = Client()
    client.run()
