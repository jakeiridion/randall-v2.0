import os
from datetime import datetime, timedelta
import subprocess
import ntpath
from pathlib import PurePath
from src.shared.Logger import create_logger
from src.server.Config import config
import re


class FolderStructure:
    def __init__(self, ip):
        self.__logger = create_logger(__name__, config.DebugMode, "server.log")
        self.__logger.debug(f"[{ip}]: Initializing FolderStructure Class...")
        self.__ip = ip
        self.__cams_dir_path = os.path.join(config.StoragePath, "cams")
        self.__ip_camera_path = os.path.join(self.__cams_dir_path, self.__ip)
        if not os.path.isdir(self.__cams_dir_path):
            self.__logger.debug(f"[Server]: creating directory {self.__cams_dir_path}")
            os.mkdir(self.__cams_dir_path)
        if not os.path.isdir(self.__ip_camera_path):
            self.__logger.debug(f"[{ip}]: creating directory {self.__ip_camera_path}.")
            os.mkdir(self.__ip_camera_path)
        self.__remove_temp_files_if_found()
        self.__logger.debug(f"[{ip}]: FolderStructure Class initialized.")

    def get_output_path(self):
        folder_date_name = datetime.now().strftime('%Y-%m-%d')
        folder_path = os.path.join(self.__ip_camera_path, folder_date_name)
        if not os.path.isdir(folder_path):
            self.__logger.debug(f"[{self.__ip}]: creating directory {folder_path}.")
            os.mkdir(folder_path)
        filename = datetime.now().strftime("%H_%M_%S.raw")
        return os.path.join(folder_path, filename)

    def get_rename_output_path(self, path):
        new_path = path.rstrip(".raw") + datetime.now().strftime("-%H_%M_%S.raw")
        return new_path

    @staticmethod
    def rename_file_if_not_renamed(file_path, log):
        if not FolderStructure.was_renamed(file_path):
            FolderStructure.__rename_file(file_path, log)

    @staticmethod
    def was_renamed(file_path):
        if "-" in ntpath.basename(file_path):
            return True
        return False

    @staticmethod
    def is_temp_file(file_path):
        if file_path.endswith(".temp"):
            return True
        return False

    @staticmethod
    def __rename_file(file_path, log):
        log.debug(f"[Server]: creating new name for unfinished file {file_path}...")
        get_video_length_command = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-sexagesimal",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        log.debug("[Server]: starting ffprobe process...")
        proc = subprocess.run(get_video_length_command, stdout=subprocess.PIPE)
        log.debug("[Server]: ffprobe process finished.")
        log.debug("[Server]: building new name...")
        video_length = proc.stdout.decode().strip()
        fmt_video_length = datetime.strptime(video_length, "%H:%M:%S.%f")
        # TODO: look for other rstrip/strip errors like this one:
        video_name = os.path.splitext(ntpath.basename(file_path))[0]
        video_start_time = datetime.strptime(video_name, "%H_%M_%S")
        new_video_name_fmt = timedelta(hours=fmt_video_length.hour, minutes=fmt_video_length.minute,
                                       seconds=fmt_video_length.second) + video_start_time
        new_video_name = video_name + datetime.strftime(new_video_name_fmt, "-%H_%M_%S.mp4")
        pure_path = PurePath(file_path)
        new_file_path = list(pure_path.parts)
        new_file_path[-1] = new_video_name
        new_file_path = os.path.join(*new_file_path)
        log.debug(f"[Server]: renaming file {file_path} to {new_file_path}.")
        os.rename(file_path, new_file_path)

    @staticmethod
    def get_file_names_from_concat_file(concat_file_paths_from_file):
        pattern = re.compile(r"'([^']+)'")
        return sorted([pattern.search(file_path).group(1) for file_path in concat_file_paths_from_file])

    @staticmethod
    def create_concat_output_file_name(file_paths):
        pattern = re.compile(r"(?!.*-).+")
        return pattern.sub(pattern.search(file_paths[-1]).group(0), file_paths[0])

    @staticmethod
    def delete_files_of_concat_file(file_paths):
        for file in file_paths:
            os.remove(file)

    def __remove_temp_files_if_found(self):
        self.__logger.debug(f"[{self.__ip}]: looking for leftover temporary files.")
        for root, dirs, files in os.walk(self.__ip_camera_path):
            for name in files:
                path = os.path.join(root, name)
                if FolderStructure.is_temp_file(path):
                    self.__logger.debug(f"[{self.__ip}]: leftover temporary concat file found: {path}")
                    os.remove(path)
                    self.__logger.debug(f"[{self.__ip}]: concat file {path} removed.")
