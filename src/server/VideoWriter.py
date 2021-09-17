from FolderStructure import FolderStructure
from VideoEncoder import VideoEncoder
from src.shared.Logger import create_logger
from src.server.Config import config
import multiprocessing as mp
from threading import Thread
import ctypes
import struct
import os
import time
from datetime import timedelta


class VideoWriter:
    def __init__(self, resolution, fps, is_running, ip, pipe):
        self.__logger = create_logger(__name__, config.DebugMode, "server.log")
        self.__logger.debug(f"[{ip}]: Initializing VideoWriter Class...")
        self.__width, self.__height = resolution
        self.__fps = fps
        self.__is_running = is_running
        self.__ip = ip
        self.__pipe_out = pipe
        self.__folder_structure = FolderStructure(ip)
        self.__logger.debug(f"[{ip}]: VideoWriter Class initialized.")

    def start_writing_video(self, to_be_encoded_pipe_in):
        self.__logger.debug(f"[{self.__ip}]: starting video writing process...")
        write_video_process = mp.Process(
            target=self.__write_video,
            args=(self.__is_running, self.__pipe_out, to_be_encoded_pipe_in, self.__logger, self.__ip),
            daemon=True)
        write_video_process.start()
        return write_video_process

    def __write_video(self, is_running, pipe_out, encoding_pipe_in, log, ip):
        cut_bool = mp.Value(ctypes.c_bool, True)
        if not config.VideoCutTime:
            self.__start_cut_timer_thread(cut_bool, is_running, log, ip)
        while is_running.value:
            output_path = self.__folder_structure.get_output_path()
            self.__create_and_write_to_output_file(output_path, cut_bool, is_running, pipe_out, log, ip)
            new_output_path = self.__folder_structure.rename_output_file(output_path)
            encoding_pipe_in.send(
                (3, VideoEncoder.get_ffmpeg_command(new_output_path, self.__width, self.__height, self.__fps)))

    def __start_cut_timer_thread(self, cut_bool, is_running, log, ip):
        log.debug(f"[{ip}]: starting cut timer thread...")
        cut_timer_thread = Thread(target=self.__cut_timer, args=[cut_bool, is_running], daemon=True)
        cut_timer_thread.start()

    def __cut_timer(self, cut_bool, is_running):
        while is_running.value:
            if cut_bool.value:
                continue
            time.sleep(self.__calculate_cut_timer())
            cut_bool.value = True

    def __calculate_cut_timer(self):
        return timedelta(hours=config.VideoCutTime.hour, minutes=config.VideoCutTime.minute,
                         seconds=config.VideoCutTime.second).seconds

    def __create_and_write_to_output_file(self, output_path, cut_bool, is_running, pipe_out, log, ip):
        log.debug(f"[{ip}]: creating new file: {output_path}.")
        with open(output_path, "wb") as file:
            self.__write_extended_attributes(output_path)
            log.debug(f"[{ip}]: writing to {output_path}...")
            cut_bool.value = False
            while is_running.value and not cut_bool.value:
                frame = pipe_out.recv_bytes()
                file.write(frame)
        log.debug(f"[{ip}]: stopped writing to {output_path}.")

    def __write_extended_attributes(self, file_path):
        self.__logger.debug(f"[{self.__ip}]: writing metadata to {file_path}.")
        os.setxattr(file_path, "user.width", struct.pack(">H", self.__width))
        os.setxattr(file_path, "user.height", struct.pack(">H", self.__height))
        os.setxattr(file_path, "user.fps", struct.pack(">H", self.__fps))
