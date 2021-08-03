from FolderStructure import FolderStructure
from VideoEncoder import VideoEncoder
from src.shared.Logger import create_logger
from Config import config
import multiprocessing as mp
from threading import Thread
import ctypes
import struct
import os
import time
from datetime import datetime, timedelta


class VideoWriter:
    def __init__(self, resolution, fps, is_running, ip, pipe):
        self.__logger = create_logger(__name__, config.debug_mode, "server.log")
        self.__logger.debug(f"[{ip}]: Initializing VideoWriter Class...")
        self.__width, self.__height = resolution
        self.__fps = fps
        self.__is_running = is_running
        self.__ip = ip
        self.__pipe_out = pipe
        self.__folder_structure = FolderStructure(ip)
        self.__logger.debug(f"[{ip}]: VideoWriter Class initialized.")

    def start_writing_video(self, to_be_encoded_pipe_in):
        output_path = self.__folder_structure.get_output_path()
        self.__logger.debug(f"[{self.__ip}]: starting video writing process...")
        write_video_process = mp.Process(
            target=self.__write_video,
            args=(output_path, self.__is_running, self.__pipe_out, to_be_encoded_pipe_in, self.__logger, self.__ip),
            daemon=True)
        write_video_process.start()
        return write_video_process

    def __write_video(self, output_path, is_running, pipe_out, encoding_pipe_in, log, ip):
        cut_bool = mp.Value(ctypes.c_bool, False)
        log.debug(f"[{ip}]: starting cut timer thread...")
        cut_timer_thread = Thread(target=self.__cut_timer, args=[cut_bool, is_running], daemon=True)
        cut_timer_thread.start()
        while is_running.value:
            log.debug(f"[{ip}]: creating new file: {output_path}.")
            with open(output_path, "wb") as file:
                self.__write_extended_attributes(output_path)
                log.debug(f"[{ip}]: writing to {output_path}...")
                while is_running.value and not cut_bool.value:
                    frame = pipe_out.recv_bytes()
                    file.write(frame)
            log.debug(f"[{ip}]: stopped writing to new file.")
            new_output_path = self.__folder_structure.get_rename_output_path(output_path)
            os.rename(output_path, new_output_path)
            log.debug(f"[{ip}]: renamed {output_path} to {new_output_path}.")
            output_path = new_output_path
            log.debug(f"[{ip}]: queueing {new_output_path} to be encoded.")
            encoding_pipe_in.send(
                VideoEncoder.get_ffmpeg_command(new_output_path, self.__width, self.__height, self.__fps))
            cut_bool.value = False

    def __cut_timer(self, cut_bool, is_running):
        while is_running.value:
            time.sleep(self.__calculate_cut_timer().seconds)
            cut_bool.value = True

    def __calculate_cut_timer(self):
        current_time = datetime.now().replace(microsecond=0)
        delta = timedelta(minutes=30) + current_time
        delta = delta.replace(minute=0, second=0, microsecond=0)
        return delta - current_time

    def __write_extended_attributes(self, file_path):
        self.__logger.debug(f"[{self.__ip}]: writing metadata to {file_path}.")
        os.setxattr(file_path, "user.width", struct.pack(">H", self.__width))
        os.setxattr(file_path, "user.height", struct.pack(">H", self.__height))
        os.setxattr(file_path, "user.fps", struct.pack(">H", self.__fps))
