import os
from datetime import datetime


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
        filename = datetime.now().strftime("%H:%M:%S.raw")
        return f"../../cams/{self.__ip}/{folder_date_name}/{filename}"

    def get_rename_output_path(self, path):
        new_path = path.rstrip(".raw") + f" - {datetime.now().strftime('%H:%M:%S.raw')}"
        return new_path
