import platform
import subprocess

from FolderStructure import FolderStructure
import multiprocessing as mp
import ctypes
import os
import time
from datetime import datetime, timedelta


class VideoWriter:
    def __init__(self, resolution, fps, is_running, ip, pipe):
        self.__width, self.__height = resolution
        self.__fps = str(fps)
        self.__is_running = is_running
        self.__ip = ip
        self.__pipe_out = pipe
        self.__folder_structure = FolderStructure(ip)
        self.__ffmpeg_path = "../../dependencies/macOS/ffmpeg" if platform.system() == "Darwin" else \
            "../../dependencies/linux/ffmpeg"

    def start_writing_video(self):
        output_path = self.__folder_structure.get_output_path()
        cut_bool = mp.Value(ctypes.c_bool, False)
        cut_timer_process = mp.Process(target=self.__cut_timer, args=(cut_bool, self.__is_running), daemon=True)
        write_video_process = mp.Process(
            target=self.__write_video,
            args=(output_path, cut_bool, self.__is_running, self.__pipe_out, cut_timer_process), daemon=True)
        cut_timer_process.start()
        write_video_process.start()
        return write_video_process

    def __write_video(self, output_path, cut_bool, is_running, pipe_out, cut_process):
        while is_running.value:
            # TODO: add xattr after creating file
            with open(output_path, "wb") as file:
                while is_running.value and not cut_bool.value:
                    frame = pipe_out.recv_bytes()
                    file.write(frame)
            new_output_path = self.__folder_structure.get_rename_output_path(output_path)
            os.rename(output_path, new_output_path)
            # start ffmpeg on raw file
            self.__encode_raw_video(new_output_path, self.__ffmpeg_path, self.__width, self.__height, self.__fps)
            cut_bool.value = False
        cut_process.terminate()

    def write_extended_attributes(self, file_path):
        if platform.system() == "Darwin":
            os.system(f"xattr -w user.width {self.__width} {file_path}")
            os.system(f"xattr -w user.height {self.__height} {file_path}")
            os.system(f"xattr -w user.fps {self.__fps} {file_path}")
        else:
            # TODO: make for linux
            pass

    @staticmethod
    def __encode_raw_video(input_path, ffmpeg_path, width, height, fps):
        final_output_path = input_path.rstrip(".raw") + ".mp4"
        ffmpeg_command = [
            ffmpeg_path,
            "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-video_size", f"{width}x{height}",
            "-pixel_format", "bgr24",
            "-framerate", fps,
            "-i", input_path,
            "-c:v", "libx265",
            "-preset", "superfast",
            "-crf", "30",
            "-b:v", "5000k",
            "-an",
            final_output_path
        ]
        proc = subprocess.Popen(ffmpeg_command, stderr=subprocess.DEVNULL)
        proc.wait()
        os.remove(input_path)

    def __cut_timer(self, cut_bool, is_running):
        while is_running.value:
            time.sleep(self.__calculate_cut_timer().seconds)
            cut_bool.value = True

    def __calculate_cut_timer(self):
        current_time = datetime.now().replace(microsecond=0)
        delta = timedelta(hours=1) + current_time
        delta.replace(minute=0, second=0, microsecond=0)
        return delta - current_time

    @staticmethod
    def encode_all_unfinished_raw_files():
        raw_files = []
        for root, dirs, files in os.walk("cams/"):
            for name in files:
                if os.path.join(root, name).endswith(".raw"):
                    raw_files.append(os.path.join(root, name))

        for raw_file in raw_files:
            pass
