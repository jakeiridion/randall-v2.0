import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(sys.path[0])))
from src.shared.Logger import create_logger
from src.server.Config import config
import multiprocessing as mp
import ctypes
import socket
from threading import Thread
import struct
from VideoWriter import VideoWriter
from VideoEncoder import VideoEncoder
import subprocess
from FolderStructure import FolderStructure
from Webserver import Webserver


class Server:
    def __init__(self):
        self.__logger = create_logger(__name__, config.DebugMode, "server.log")
        self.__logger.debug("[Server]: Initializing Server Class...")
        # Client Connections
        self.__management_connections = {}
        self.__stream_connections = {}
        # Processes
        self.__camera_processes = {}
        self.__server_processes_threads = []
        # Variables
        self.__is_running = mp.Value(ctypes.c_bool, True)
        self.__height = config.DefaultHeight
        self.__width = config.DefaultWidth
        self.__ip = config.ServerIP
        self.__port = config.ServerPort
        self.__consecutive_ffmpeg_threads = config.ConsecutiveFFMPEGThreads
        # Network
        self.__tcp_sock = self.__create_tcp_socket()
        # Webserver
        self.webserver = Webserver.Webserver()
        # Video Encoder
        self.__to_be_encoded_out, self.__to_be_encoded_in = mp.Pipe(False)
        self.__start_handling_unencoded_files_thread()
        VideoEncoder.encode_rename_and_delete_all_unfinished_raw_files(self.__to_be_encoded_in, self.__logger)
        # Start Network listening
        self.__start_handling_new_connections_thread()
        self.__logger.debug("[Server]: Server Class Initialized.")

    def __create_tcp_socket(self):
        self.__logger.debug("[Server]: creating tcp socket...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        sock.setblocking(True)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 360448)
        # print(sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF))
        sock.bind((self.__ip, self.__port))
        self.__logger.debug("[Server]: tcp socket created.")
        return sock

    def __start_handling_unencoded_files_thread(self):
        self.__logger.debug("[Server]: handling unencoded files...")

        def loop(is_running, log, consecutive_ffmpeg_threads, pipe):
            while is_running.value:
                current_running_ffmpeg_processes = []
                for _ in range(consecutive_ffmpeg_threads):
                    ffmpeg_command = pipe.recv()
                    log.debug("[Server]: ffmpeg command received.")
                    proc = subprocess.Popen(ffmpeg_command, stderr=subprocess.DEVNULL, shell=True)
                    log.debug(f"[Server]: ffmpeg process started with {proc.pid} PID.")
                    current_running_ffmpeg_processes.append((proc, ffmpeg_command.split(" ")[-4]))  # file path
                for proc, file_path in current_running_ffmpeg_processes:
                    proc.wait()
                    log.debug(f"[Server]: ffmpeg process with {proc.pid} PID finished.")
                    FolderStructure.rename_file_if_not_renamed(file_path, self.__logger)
            log.debug("[Server]: stopped handling unencoded files.")

        Thread(target=loop, args=[self.__is_running, self.__logger, self.__consecutive_ffmpeg_threads,
                                  self.__to_be_encoded_out], daemon=True).start()

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
            fps = 30
            while True:
                try:
                    request = conn.recv(2)
                except OSError:
                    # When connection was closed properly.
                    self.__logger.debug(f"[{ip}]: connection dead.")
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
                # set fps
                elif request == b"sf":
                    log.debug(f"[{ip}]: sending fps...")
                    fps = int(struct.unpack(">B", conn.recv(struct.calcsize(">B")))[0])
                # start stream
                elif request == struct.pack(">?", True):
                    log.debug(f"[{ip}]: requests stream start...")
                    self.__start_stream(log, is_running, height, width, ip, conn, fps)
                # client crashed
                elif request == b"":
                    self.__handle_client_crash(is_running, ip)
                    break
            log.debug(f"[{ip}]: stopped listening for commands.")

        t = Thread(target=loop, args=[self.__logger, connection, ip_address, self.__height, self.__width], daemon=True)
        t.start()

    def __start_stream(self, log, is_running, height, width, ip, conn, fps):
        log.debug(f"[{ip}] starting stream...")
        is_running.value = True
        pipe_out, pipe_in = mp.Pipe(False)
        video_writer = VideoWriter((width, height), fps, is_running, ip, pipe_out)
        self.webserver.resolutions[ip] = (height, width)
        self.__handle_stream_connection(is_running, pipe_in, height, width, ip, self.__stream_connections[ip],
                                        self.webserver.frames)
        p = video_writer.start_writing_video(self.__to_be_encoded_in)
        self.__camera_processes[ip].append(p)
        conn.send(struct.pack(">?", True))

    def __handle_stream_connection(self, is_running, pipe_in, height, width, ip_address, stream_connection,
                                   webserver_frames):
        def loop(log, ip, conn, h, w, is_run, pipe, ws_frames):
            log.debug(f"[{ip}]: stream started.")
            frame_byte_size = h * w * 3
            while is_run.value:
                buffer = b""
                while len(buffer) < frame_byte_size and is_run.value:
                    buffer += conn.recv(frame_byte_size-len(buffer))
                pipe.send_bytes(buffer)
                ws_frames[ip] = buffer
            log.debug(f"[{ip}]: stream stopped..")
            # TODO: handle webserver stream stop.

        p = mp.Process(target=loop, args=(self.__logger, ip_address, stream_connection, height, width,
                                          is_running, pipe_in, webserver_frames), daemon=True)
        p.start()
        self.__camera_processes[ip_address] = [p]

    def __handle_client_crash(self, is_running, ip):
        self.__logger.warning("Client crashed!")
        self.__logger.info("Handling client crash...")
        is_running.value = False
        self.__join_all_client_processes(ip)
        self.webserver.delete_camera(ip)
        self.__close_client_connections(ip)
        self.__logger.info("Client crash handled.")

    def __join_all_client_processes(self, ip):
        self.__logger.debug(f"[Server]: joining all processes of client {ip}...")
        for item in self.__camera_processes[ip]:
            self.__logger.debug(f"[Server]: joining process: {item} of client {ip}")
            item.join(timeout=15)
            self.__logger.debug(f"[Server]: process: {item} of client {ip} joined.")
        self.__logger.debug(f"[Server]: all processes of client {ip} joined.")
        del self.__camera_processes[ip]

    def __close_client_connections(self, ip):
        self.__logger.debug(f"[{ip}]: closing socket connections...")
        self.__management_connections[ip].close()
        self.__logger.debug(f"[{ip}]: management connection closed.")
        self.__stream_connections[ip].close()
        self.__logger.debug(f"[{ip}]: stream connection closed.")
        self.__clear_client_from_connections_dict(ip)
        self.__logger.debug(f"[{ip}]: socket connections closed.")

    def __clear_client_from_connections_dict(self, ip):
        self.__logger.debug(f"[{ip}]: deleting client connections from server memory...")
        del self.__management_connections[ip]
        self.__logger.debug(f"[{ip}]: management connection deleted.")
        del self.__stream_connections[ip]
        self.__logger.debug(f"[{ip}]: stream connection deleted.")

    def stop_all_streams(self):
        for key in self.__management_connections:
            self.__management_connections[key].send(struct.pack(">?", False))
            self.__join_all_client_processes(key)

    def restart_stream(self):
        for key in self.__management_connections:
            self.__management_connections[key].send(struct.pack(">?", True))

    def quit_all_clients(self):
        pass


if __name__ == '__main__':
    server = Server()
    server.webserver.run_webserver()
