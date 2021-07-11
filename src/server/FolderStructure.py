import os
from datetime import datetime, timedelta
import subprocess


# TODO: work with os.path.dirname
class FolderStructure:
    def __init__(self, ip):
        self.__ip = ip
        if not os.path.isdir("../../cams"):
            os.mkdir("../../cams")
        if not os.path.isdir(f"../../cams/{ip}"):
            os.mkdir(f"../../cams/{ip}")

    def get_output_path(self):
        folder_date_name = datetime.now().strftime('%Y-%m-%d')
        if not os.path.isdir(f"../../cams/{self.__ip}/{folder_date_name}"):
            os.mkdir(f"../../cams/{self.__ip}/{folder_date_name}")
        filename = datetime.now().strftime("%H_%M_%S.raw")
        return f"../../cams/{self.__ip}/{folder_date_name}/{filename}"

    def get_rename_output_path(self, path):
        new_path = path.rstrip(".raw") + datetime.now().strftime("-%H_%M_%S.raw")
        return new_path

    @staticmethod
    def rename_file_if_left_unfinished(file_path):
        if "-" not in file_path.split("/")[-1]:
            FolderStructure.__rename_newly_encoded_file(file_path)

    # TODO: use ntpath to get filenames
    @staticmethod
    def __rename_newly_encoded_file(file_path):
        get_video_length_command = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-sexagesimal",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        proc = subprocess.run(get_video_length_command, stdout=subprocess.PIPE)
        video_length = proc.stdout.decode().strip()
        fmt_video_length = datetime.strptime(video_length, "%H:%M:%S.%f")
        video_name = file_path.split("/")[-1].rstrip(".mp4")
        video_start_time = datetime.strptime(video_name, "%H_%M_%S")
        new_video_name_fmt = timedelta(hours=fmt_video_length.hour, minutes=fmt_video_length.minute,
                                       seconds=fmt_video_length.second) + video_start_time
        new_video_name = video_name + datetime.strftime(new_video_name_fmt, "-%H_%M_%S.mp4")
        new_video_path = file_path.split("/")
        new_video_path[-1] = new_video_name
        new_video_path = "/".join(new_video_path)
        os.rename(file_path, new_video_path)
        return new_video_path
