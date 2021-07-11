from FolderStructure import FolderStructure
from VideoEncoder import VideoEncoder
import multiprocessing as mp
from threading import Thread
import ctypes
import struct
import os
import time
from datetime import datetime, timedelta


class VideoWriter:
    def __init__(self, resolution, fps, is_running, ip, pipe):
        self.__width, self.__height = resolution
        self.__fps = fps
        self.__is_running = is_running
        self.__ip = ip
        self.__pipe_out = pipe
        self.__folder_structure = FolderStructure(ip)

    def start_writing_video(self, to_be_encoded_pipe_in):
        output_path = self.__folder_structure.get_output_path()
        write_video_process = mp.Process(
            target=self.__write_video,
            args=(output_path, self.__is_running, self.__pipe_out, to_be_encoded_pipe_in), daemon=True)
        write_video_process.start()
        return write_video_process

    def __write_video(self, output_path, is_running, pipe_out, encoding_pipe_in):
        cut_bool = mp.Value(ctypes.c_bool, False)
        cut_timer_thread = Thread(target=self.__cut_timer, args=[cut_bool, is_running], daemon=True)
        cut_timer_thread.start()
        while is_running.value:
            with open(output_path, "wb") as file:
                self.__write_extended_attributes(output_path)
                while is_running.value and not cut_bool.value:
                    frame = pipe_out.recv_bytes()
                    file.write(frame)
            new_output_path = self.__folder_structure.get_rename_output_path(output_path)
            os.rename(output_path, new_output_path)
            output_path = new_output_path
            encoding_pipe_in.send(
                VideoEncoder.get_ffmpeg_command(new_output_path, self.__width, self.__height, self.__fps))
            cut_bool.value = False

    def __cut_timer(self, cut_bool, is_running):
        while is_running.value:
            time.sleep(self.__calculate_cut_timer().seconds)
            cut_bool.value = True

    def __calculate_cut_timer(self):
        current_time = datetime.now().replace(microsecond=0)
        delta = timedelta(hours=1) + current_time
        delta = delta.replace(minute=0, second=0, microsecond=0)
        return delta - current_time

    def __write_extended_attributes(self, file_path):
        os.setxattr(file_path, "user.width", struct.pack(">H", self.__width))
        os.setxattr(file_path, "user.height", struct.pack(">H", self.__height))
        os.setxattr(file_path, "user.fps", struct.pack(">H", self.__fps))
