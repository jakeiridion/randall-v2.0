import os
from datetime import datetime, timedelta
import ntpath
from pathlib import PurePath
from src.shared.Logger import create_logger
from src.server.Config import config
import re
import struct
import shutil
import time
from VideoEncoder import VideoEncoder


class FolderStructure:
    def __init__(self, ip):
        self.__logger = create_logger(__name__, config.DebugMode, "server.log")
        self.__logger.debug(f"[{ip}]: Initializing FolderStructure Class...")
        self.__ip = ip
        self.__cams_dir_path = os.path.join(config.StoragePath, "cams")
        self.__ip_camera_path = os.path.join(self.__cams_dir_path, ip)
        self.__init_client_folder_structure()
        self.__logger.debug(f"[{ip}]: FolderStructure Class initialized.")

    def __init_client_folder_structure(self):
        self.__logger.debug(f"[{self.__ip}]: Initializing Client Folder Structure.")
        self.__create_cams_dir_if_necessary()
        self.__create_ip_camera_dir_if_necessary()
        self.__remove_temp_files_if_found()
        self.__logger.debug(f"[{self.__ip}]: Client Folder Structure initialized.")

    def __create_cams_dir_if_necessary(self):
        if not os.path.isdir(self.__cams_dir_path):
            self.__logger.debug(f"[{self.__ip}]: creating directory {self.__cams_dir_path}.")
            os.mkdir(self.__cams_dir_path)

    def __create_ip_camera_dir_if_necessary(self):
        if not os.path.isdir(self.__ip_camera_path):
            self.__logger.debug(f"[{self.__ip}]: creating directory {self.__ip_camera_path}.")
            os.mkdir(self.__ip_camera_path)

    def __remove_temp_files_if_found(self):
        self.__logger.debug(f"[{self.__ip}]: looking for leftover temporary files.")
        for temp_file in FolderStructure.__get_all_temp_files(self.__logger):
            self.__logger.debug(f"[{self.__ip}]: leftover temporary concat file found: {temp_file}")
            os.remove(temp_file)
            self.__logger.debug(f"[{self.__ip}]: concat file {temp_file} removed.")

    def get_output_path(self):
        folder_date_name = datetime.now().strftime('%Y-%m-%d')
        folder_path = os.path.join(self.__ip_camera_path, folder_date_name)
        if not os.path.isdir(folder_path):
            self.__logger.debug(f"[{self.__ip}]: creating directory {folder_path}.")
            os.mkdir(folder_path)
        filename = datetime.now().strftime("%H_%M_%S.raw")
        return os.path.join(folder_path, filename)

    def rename_output_file(self, output_path):
        new_output_path = self.__get_rename_output_path(output_path)
        os.rename(output_path, new_output_path)
        self.__logger.debug(f"[{self.__ip}]: renamed {output_path} to {new_output_path}.")
        self.__logger.debug(f"[{self.__ip}]: queueing {new_output_path} to be encoded.")
        return new_output_path

    def __get_rename_output_path(self, path):
        new_path = path.rstrip(".raw") + datetime.now().strftime("-%H_%M_%S.raw")
        return new_path

    @staticmethod
    def encode_rename_and_delete_all_unfinished_raw_files(encoding_queue, log):
        log.debug("[Server]: looking for leftover unfinished or unencoded files...")
        raw_files, to_be_renamed = FolderStructure.__find_unfinished_files(log)
        FolderStructure.__handle_raw_files(raw_files, encoding_queue, log)
        FolderStructure.__handled_unnamed_files(to_be_renamed, raw_files, log)
        log.debug("[Server]: handled unfinished files.")

    @staticmethod
    def __get_all_temp_files(log):
        log.debug("[Server]: looking for all temp files...")
        temp_files = list(filter(
            lambda file: FolderStructure.is_temp_file(file),
            FolderStructure.__get_all_files_from_cam_dir()
        ))
        log.debug("[Server]: finished looking for temp files.")
        return temp_files

    @staticmethod
    def __find_unfinished_files(log):
        cam_files = FolderStructure.__get_all_files_from_cam_dir()
        raw_files = list(filter(
            lambda file: file.endswith(".raw"),
            cam_files
        ))
        to_be_renamed = list(filter(
            lambda file: not FolderStructure.was_renamed(file) and not FolderStructure.is_temp_file(file),
            cam_files
        ))

        for raw_file in raw_files:
            log.debug(f"[Server]: leftover raw file found: {raw_file}")
        for tbr in to_be_renamed:
            log.debug(f"[Server]: not renamed video file found: {tbr}")

        return raw_files, to_be_renamed

    @staticmethod
    def __get_all_files_from_cam_dir():
        all_cam_files = []
        for root, dirs, files in os.walk(os.path.join(config.StoragePath, "cams")):
            for name in files:
                path = os.path.join(root, name)
                all_cam_files.append(path)
        return all_cam_files

    @staticmethod
    def __handle_raw_files(raw_files, encoding_queue, log):
        log.debug("[Server]: handling leftover raw files...")
        for raw_file in raw_files:
            log.debug(f"[Server]: unpacking metadata from {raw_file}")
            width, height, fps = tuple(struct.unpack(">H", os.getxattr(raw_file, attr))[0]
                                       for attr in os.listxattr(raw_file))
            log.debug(f"[Server]: sending {raw_file} to be encoded.")
            encoding_queue.put((2, VideoEncoder.get_ffmpeg_command(raw_file, width, height, fps)))
        log.debug("[Server]: leftover raw files handled.")

    @staticmethod
    def __handled_unnamed_files(to_be_renamed, raw_files, log):
        log.debug("[Server]: handling unnamed files...")
        for unnamed_file_path in to_be_renamed:
            if re.sub(rf"{config.OutputFileExtension}$", ".raw", unnamed_file_path) not in raw_files:
                FolderStructure.rename_file_if_not_renamed(unnamed_file_path, log)
        log.debug("[Server]: unnamed files handled.")

    @staticmethod
    def is_temp_file(file_path):
        if file_path.endswith(".temp"):
            return True
        return False

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
    def __rename_file(file_path, log):
        log.debug(f"[Server]: creating new name for unfinished file {file_path}...")
        proc = VideoEncoder.get_video_length(file_path, log)
        FolderStructure.__rename_if_ffprobe_successful(proc, file_path, log)

    @staticmethod
    def __rename_if_ffprobe_successful(proc, file_path, log):
        if proc.returncode == 0:
            new_file_path = FolderStructure.__build_new_file_path_from_ffprobe_result(proc, file_path, log)
            log.debug(f"[Server]: renaming file {file_path} to {new_file_path}.")
            os.rename(file_path, new_file_path)

    @staticmethod
    def __build_new_file_path_from_ffprobe_result(proc, file_path, log):
        log.debug("[Server]: building new name...")
        video_length = proc.stdout.decode().strip()
        fmt_video_length = datetime.strptime(video_length, "%H:%M:%S.%f")
        video_name = os.path.splitext(ntpath.basename(file_path))[0]
        video_start_time = datetime.strptime(video_name, "%H_%M_%S")
        new_video_name_fmt = timedelta(hours=fmt_video_length.hour, minutes=fmt_video_length.minute,
                                       seconds=fmt_video_length.second) + video_start_time
        new_video_name = video_name + datetime.strftime(new_video_name_fmt, f"-%H_%M_%S{config.OutputFileExtension}")
        pure_path = PurePath(file_path)
        new_file_path = list(pure_path.parts)
        new_file_path[-1] = new_video_name
        return os.path.join(*new_file_path)

    @staticmethod
    def add_to_be_concat(file_path, log):
        concat_file_path = os.path.join(os.path.dirname(file_path), "to_be_concat.temp")
        FolderStructure.__add_to_concat_file(file_path, concat_file_path, log)
        lines = FolderStructure.__get_concat_file_lines(concat_file_path)
        if len(lines) == config.ConcatAmount:
            log.debug("[Server]: concat amount reached.")
            FolderStructure.__perform_video_concat(concat_file_path, log)

    @staticmethod
    def __add_to_concat_file(file_path, concat_file_path, log):
        log.debug(f"[Server]: adding {file_path} to concat file: {concat_file_path}.")
        with open(concat_file_path, "a") as concat_file:
            concat_file.write(f"file '{file_path}'\n")

    @staticmethod
    def __get_concat_file_lines(concat_file_path):
        with open(concat_file_path, "r") as concat_file:
            lines = sorted(concat_file.readlines())
        return lines

    @staticmethod
    def __perform_video_concat(concat_file_path, log):
        log.debug(f"[Server]: concatenating files in concat file: {concat_file_path}")
        concat_file_paths = FolderStructure.__get_file_names_from_concat_file(concat_file_path)
        log.debug("[Server]: creating new output name...")
        output_name = FolderStructure.__create_concat_output_file_name(concat_file_paths)
        log.debug(f"[Server]: new output name created: {output_name}")
        log.debug("[Server]: joining video files...")
        rc = VideoEncoder.concat_video_files(concat_file_path, output_name, log)
        FolderStructure.__cleanup_concat_if_successful(rc, concat_file_path, concat_file_paths, log)
        return rc

    @staticmethod
    def __get_file_names_from_concat_file(concat_file_path):
        lines = FolderStructure.__get_concat_file_lines(concat_file_path)
        pattern = re.compile(r"'([^']+)'")
        return sorted([pattern.search(file_path).group(1) for file_path in lines])

    @staticmethod
    def __create_concat_output_file_name(file_paths):
        pattern = re.compile(r"(?!.*-).+")
        return pattern.sub(pattern.search(file_paths[-1]).group(0), file_paths[0])

    @staticmethod
    def __cleanup_concat_if_successful(rc, concat_file_path, concat_file_paths, log):
        if rc == 0:
            log.debug("[Server]: Deleting old files...")
            os.remove(concat_file_path)
            log.debug("[Server]: Concat file deleted.")
            FolderStructure.__delete_files_of_concat_file(concat_file_paths)
            log.debug("[Server]: Video files deleted.")
            log.debug("[Server]: Old files deleted.")

    @staticmethod
    def __delete_files_of_concat_file(file_paths):
        for file in file_paths:
            os.remove(file)

    @staticmethod
    def concat_all_temp_files(log):
        log.debug("[Server]: Performing concatenation process with all Client concat files...")
        temp_files = FolderStructure.__get_all_temp_files(log)
        return_codes = set()
        for temp_file in temp_files:
            rc = FolderStructure.__perform_video_concat(temp_file, log)
            return_codes.add(rc)
        # TODO: handle rc
        log.debug("[Server]: All Client concat file entries concatenated.")

    @staticmethod
    def monitor_free_disk_space(is_running, log):
        log.debug("[Server]: start monitoring free disk space...")
        while is_running.value:
            disk_space = FolderStructure.__get_free_disk_space_in_bytes()
            if disk_space and disk_space <= config.FreeStorageAmountBeforeDeleting:
                log.debug(f"[Server]: Disk Space reached: {config.FreeStorageAmountBeforeDeleting} bytes.")
                FolderStructure.__delete_oldest_camera_recording(log)
            time.sleep(10)
        log.debug("[Server]: stopped monitoring free disk space.")

    @staticmethod
    def __get_free_disk_space_in_bytes():
        try:
            total, used, free = shutil.disk_usage(config.StoragePath)
            return free
        except FileNotFoundError:
            return 0

    @staticmethod
    def __delete_oldest_camera_recording(log):
        log.debug("[Server]: Looking for oldest video file...")
        cam_files = FolderStructure.__get_all_files_from_cam_dir()
        cam_files = list(
            filter(
                lambda cam_file:
                not FolderStructure.is_temp_file(cam_file) and not FolderStructure.__is_raw_file(cam_file),
                sorted(cam_files, key=lambda file: os.path.getmtime(file))
            )
        )
        if cam_files:
            to_be_deleted = cam_files.pop(0)
            log.debug(f"[Server]: Deleting oldest file to make space: {to_be_deleted}.")
            os.remove(to_be_deleted)
        log.debug("[Server]: Stopped looking for oldest video file.")

    @staticmethod
    def __is_raw_file(file_path):
        if file_path.endswith(".raw"):
            return True
        return False
